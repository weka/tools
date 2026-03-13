// Package planner computes ordered change sets with human-readable explanations.
package planner

import (
	"fmt"
	"log"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/sysctl"
)

// PlanChanges generates an ordered list of changes needed to establish
// correct SBR.  Changes are ordered:
//  1. Sysctl settings
//  2. Routing table entries in /etc/iproute2/rt_tables
//  3. Subnet routes in custom tables
//  4. Default routes in custom tables
//  5. IP policy rules
func PlanChanges(
	state *models.SystemState,
	validationResults []models.ValidationResult,
) []models.PlannedChange {
	// Collect failed checks by interface.
	failedByIface := make(map[string]map[string]bool)
	for _, r := range validationResults {
		if !r.IsCorrect {
			if failedByIface[r.InterfaceName] == nil {
				failedByIface[r.InterfaceName] = make(map[string]bool)
			}
			failedByIface[r.InterfaceName][r.CheckName] = true
		}
	}

	if len(failedByIface) == 0 {
		return nil
	}

	var changes []models.PlannedChange

	// Plan sysctl changes first.
	var nonDefaultIfaces []string
	for _, i := range state.Interfaces {
		if !i.IsLoopback && !i.IsDefaultRouteInterface && i.IsUp {
			nonDefaultIfaces = append(nonDefaultIfaces, i.Name)
		}
	}
	changes = append(changes, sysctl.PlanSysctlChanges(state.SysctlValues, nonDefaultIfaces)...)

	// Allocate table numbers for interfaces that need them.
	usedNumbers := make(map[int]bool)
	usedNames := make(map[string]bool)
	tableAssignments := make(map[string]int) // iface_name -> table_number

	for _, rt := range state.RoutingTables {
		usedNumbers[rt.Number] = true
		usedNames[rt.Name] = true
	}

	// Pre-populate from existing tables.
	for _, rt := range state.RoutingTables {
		prefix := constants.TableNamePrefix
		if len(rt.Name) > len(prefix) && rt.Name[:len(prefix)] == prefix {
			ifaceName := rt.Name[len(prefix):]
			tableAssignments[ifaceName] = rt.Number
		}
	}

	nextNumber := constants.TableNumberStart
	usedPriorities := make(map[int]bool)
	for _, r := range state.Rules {
		usedPriorities[r.Priority] = true
	}

	for _, iface := range state.Interfaces {
		if iface.IsLoopback || iface.IsDefaultRouteInterface || !iface.IsUp {
			continue
		}

		ifaceFails := failedByIface[iface.Name]
		if len(ifaceFails) == 0 {
			continue
		}

		tableName := constants.TableNamePrefix + iface.Name

		// Phase 1: Routing table entry.
		if ifaceFails["routing_table_exists"] {
			if _, ok := tableAssignments[iface.Name]; !ok {
				for usedNumbers[nextNumber] || constants.ReservedTableNumbers[nextNumber] {
					nextNumber++
					if nextNumber > constants.TableNumberMax {
						log.Println("[ERROR] Exhausted routing table numbers")
						break
					}
				}
				tableAssignments[iface.Name] = nextNumber
				usedNumbers[nextNumber] = true
				nextNumber++
			}

			tableNum := tableAssignments[iface.Name]
			changes = append(changes, models.PlannedChange{
				ChangeType: models.ChangeAddRTTable,
				Description: fmt.Sprintf("Add routing table %d '%s'", tableNum, tableName),
				Reason: fmt.Sprintf(
					"Interface %s has IP %s but no dedicated routing table. "+
						"Without its own table, response traffic from %s will follow "+
						"the main routing table's default route and exit via the wrong "+
						"interface, causing asymmetric routing and dropped connections "+
						"(the remote host sees replies from a different IP than it sent to).",
					iface.Name, iface.IPAddress, iface.IPAddress),
				Command:   fmt.Sprintf("echo '%d %s' >> /etc/iproute2/rt_tables", tableNum, tableName),
				Interface: models.StrPtr(iface.Name),
			})
		}

		// Phase 2: Subnet route.
		if ifaceFails["subnet_route_in_table"] {
			routeCmd := fmt.Sprintf("ip route replace %s dev %s src %s table %s",
				iface.Subnet, iface.Name, iface.IPAddress, tableName)
			delCmd := fmt.Sprintf("ip route del %s dev %s table %s",
				iface.Subnet, iface.Name, tableName)

			gwNote := ""
			if iface.Gateway != nil {
				gwNote = fmt.Sprintf("the gateway (%s) and ", *iface.Gateway)
			}

			changes = append(changes, models.PlannedChange{
				ChangeType: models.ChangeAddRoute,
				Description: fmt.Sprintf("Add subnet route %s dev %s table %s",
					iface.Subnet, iface.Name, tableName),
				Reason: fmt.Sprintf(
					"Table '%s' needs a route to the local subnet %s via %s. "+
						"This allows the custom routing table to reach %sother hosts "+
						"on the local network segment.",
					tableName, iface.Subnet, iface.Name, gwNote),
				Command:         routeCmd,
				Interface:       models.StrPtr(iface.Name),
				RollbackCommand: models.StrPtr(delCmd),
			})
		}

		// Phase 3: Default route in custom table (only if gateway exists).
		if iface.Gateway != nil && ifaceFails["default_route_in_table"] {
			gw := *iface.Gateway
			routeCmd := fmt.Sprintf("ip route replace default via %s dev %s table %s",
				gw, iface.Name, tableName)
			delCmd := fmt.Sprintf("ip route del default via %s dev %s table %s",
				gw, iface.Name, tableName)

			changes = append(changes, models.PlannedChange{
				ChangeType: models.ChangeAddRoute,
				Description: fmt.Sprintf("Add default route via %s dev %s table %s",
					gw, iface.Name, tableName),
				Reason: fmt.Sprintf(
					"Table '%s' needs a default route so that traffic originating "+
						"from %s destined for remote networks can exit through %s's "+
						"gateway (%s). Without this, only local-subnet traffic would work.",
					tableName, iface.IPAddress, iface.Name, gw),
				Command:         routeCmd,
				Interface:       models.StrPtr(iface.Name),
				RollbackCommand: models.StrPtr(delCmd),
			})
		}

		// Phase 4: IP rule.
		if ifaceFails["ip_rule_exists"] {
			priority := constants.RulePriorityStart
			for usedPriorities[priority] {
				priority += constants.RulePriorityIncrement
			}
			usedPriorities[priority] = true

			ruleCmd := fmt.Sprintf("ip rule add from %s table %s priority %d",
				iface.IPAddress, tableName, priority)
			delCmd := fmt.Sprintf("ip rule del from %s table %s priority %d",
				iface.IPAddress, tableName, priority)

			changes = append(changes, models.PlannedChange{
				ChangeType: models.ChangeAddRule,
				Description: fmt.Sprintf("Add rule: from %s lookup %s (priority %d)",
					iface.IPAddress, tableName, priority),
				Reason: fmt.Sprintf(
					"This IP policy rule tells the kernel that all traffic "+
						"originating from %s should consult table '%s' instead of "+
						"the main routing table. This is the key rule that ensures "+
						"responses leave through the same interface they arrived on.",
					iface.IPAddress, tableName),
				Command:         ruleCmd,
				Interface:       models.StrPtr(iface.Name),
				RollbackCommand: models.StrPtr(delCmd),
			})
		}
	}

	log.Printf("[INFO] Planned %d changes", len(changes))
	return changes
}
