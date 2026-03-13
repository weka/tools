// Package validator checks current state against correct SBR requirements.
package validator

import (
	"fmt"
	"log"
	"strings"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/sysctl"
)

// Validate validates the current system state for correct source-based routing.
func Validate(state *models.SystemState) []models.ValidationResult {
	var results []models.ValidationResult

	// Find the default route interface.
	defaultIface := findDefaultInterface(state)
	_ = defaultIface // used in default-route validation below

	// Validate each interface.
	for _, iface := range state.Interfaces {
		if iface.IsLoopback {
			continue
		}
		if iface.IsDefaultRouteInterface {
			gw := "unknown"
			if iface.Gateway != nil {
				gw = *iface.Gateway
			}
			results = append(results, models.ValidationResult{
				InterfaceName:  iface.Name,
				CheckName:      "default_route_interface",
				IsCorrect:      true,
				CurrentValue:   fmt.Sprintf("Default route via %s", gw),
				ExpectedValue:  "Not modified by SBR",
				FixDescription: "",
			})
			continue
		}

		if !iface.IsUp {
			results = append(results, models.ValidationResult{
				InterfaceName:  iface.Name,
				CheckName:      "interface_state",
				IsCorrect:      true,
				CurrentValue:   "DOWN (skipped)",
				ExpectedValue:  "Interface is down, skipping SBR checks",
				FixDescription: "",
			})
			continue
		}

		// Run SBR checks for this interface.
		tableName := constants.TableNamePrefix + iface.Name
		results = append(results, validateInterfaceSBR(&iface, tableName, state)...)
	}

	// Validate that the main table's default route is intact.
	results = append(results, validateDefaultRoute(state)...)

	// Validate sysctl settings.
	var nonDefaultIfaces []string
	for _, i := range state.Interfaces {
		if !i.IsLoopback && !i.IsDefaultRouteInterface && i.IsUp {
			nonDefaultIfaces = append(nonDefaultIfaces, i.Name)
		}
	}
	results = append(results, sysctl.ValidateSysctl(state.SysctlValues, nonDefaultIfaces)...)

	return results
}

func findDefaultInterface(state *models.SystemState) *models.InterfaceInfo {
	for i := range state.Interfaces {
		if state.Interfaces[i].IsDefaultRouteInterface {
			return &state.Interfaces[i]
		}
	}
	return nil
}

func validateInterfaceSBR(
	iface *models.InterfaceInfo,
	tableName string,
	state *models.SystemState,
) []models.ValidationResult {
	var results []models.ValidationResult

	// Check 1: Routing table entry exists.
	tableExists := false
	for _, rt := range state.RoutingTables {
		if rt.Name == tableName {
			tableExists = true
			break
		}
	}
	results = append(results, models.ValidationResult{
		InterfaceName: iface.Name,
		CheckName:     "routing_table_exists",
		IsCorrect:     tableExists,
		CurrentValue: fmt.Sprintf("Table '%s' %s", tableName,
			boolStr(tableExists, "exists", "missing")),
		ExpectedValue: fmt.Sprintf("Table '%s' in /etc/iproute2/rt_tables", tableName),
		FixDescription: func() string {
			if !tableExists {
				return fmt.Sprintf(
					"Interface %s (%s) needs a dedicated routing table named '%s' "+
						"so traffic from this interface can be routed independently "+
						"of the main routing table.",
					iface.Name, iface.IPAddress, tableName)
			}
			return ""
		}(),
	})

	// Check 2: Subnet route in custom table.
	tableRoutes := state.RoutesByTable[tableName]
	hasSubnetRoute := false
	for _, r := range tableRoutes {
		if r.Destination == iface.Subnet && r.Device == iface.Name {
			hasSubnetRoute = true
			break
		}
	}
	results = append(results, models.ValidationResult{
		InterfaceName: iface.Name,
		CheckName:     "subnet_route_in_table",
		IsCorrect:     hasSubnetRoute,
		CurrentValue: fmt.Sprintf("Subnet route for %s %s in table %s",
			iface.Subnet, boolStr(hasSubnetRoute, "found", "missing"), tableName),
		ExpectedValue: fmt.Sprintf("%s dev %s src %s table %s",
			iface.Subnet, iface.Name, iface.IPAddress, tableName),
		FixDescription: func() string {
			if !hasSubnetRoute {
				return fmt.Sprintf(
					"Table '%s' needs a route to the local subnet %s via %s "+
						"so the interface can reach its gateway.",
					tableName, iface.Subnet, iface.Name)
			}
			return ""
		}(),
	})

	// Check 3: Default route in custom table (only if gateway is known).
	if iface.Gateway != nil {
		gw := *iface.Gateway
		hasDefaultRoute := false
		for _, r := range tableRoutes {
			if r.Destination == "default" && r.Gateway != nil && *r.Gateway == gw && r.Device == iface.Name {
				hasDefaultRoute = true
				break
			}
		}
		results = append(results, models.ValidationResult{
			InterfaceName: iface.Name,
			CheckName:     "default_route_in_table",
			IsCorrect:     hasDefaultRoute,
			CurrentValue: fmt.Sprintf("Default route via %s dev %s %s in table %s",
				gw, iface.Name, boolStr(hasDefaultRoute, "found", "missing"), tableName),
			ExpectedValue: fmt.Sprintf("default via %s dev %s table %s",
				gw, iface.Name, tableName),
			FixDescription: func() string {
				if !hasDefaultRoute {
					return fmt.Sprintf(
						"Table '%s' needs a default route via %s so traffic "+
							"originating from %s destined for remote networks exits "+
							"through %s's gateway.",
						tableName, gw, iface.IPAddress, iface.Name)
				}
				return ""
			}(),
		})
	} else {
		results = append(results, models.ValidationResult{
			InterfaceName:  iface.Name,
			CheckName:      "default_route_in_table",
			IsCorrect:      true,
			CurrentValue:   "No gateway -- default route not applicable",
			ExpectedValue:  "No default route (non-routable interface)",
			FixDescription: "",
		})
	}

	// Check 4: IP rule exists.
	hasRule := false
	for _, r := range state.Rules {
		if r.SelectorFrom != nil && r.Table != nil &&
			(*r.SelectorFrom == iface.IPAddress || *r.SelectorFrom == iface.IPAddress+"/32") &&
			*r.Table == tableName {
			hasRule = true
			break
		}
	}
	results = append(results, models.ValidationResult{
		InterfaceName: iface.Name,
		CheckName:     "ip_rule_exists",
		IsCorrect:     hasRule,
		CurrentValue: fmt.Sprintf("Rule from %s lookup %s %s",
			iface.IPAddress, tableName, boolStr(hasRule, "found", "missing")),
		ExpectedValue: fmt.Sprintf("from %s lookup %s", iface.IPAddress, tableName),
		FixDescription: func() string {
			if !hasRule {
				return fmt.Sprintf(
					"An IP rule is needed to direct traffic originating from "+
						"%s to use table '%s'. Without this rule, the kernel uses "+
						"the main routing table and responses may exit via the wrong interface.",
					iface.IPAddress, tableName)
			}
			return ""
		}(),
	})

	// Check 5: No conflicting rules.
	var conflicting []models.Rule
	for _, r := range state.Rules {
		if r.SelectorFrom == nil || r.Table == nil {
			continue
		}
		from := *r.SelectorFrom
		tbl := *r.Table
		if (from == iface.IPAddress || from == iface.IPAddress+"/32") &&
			tbl != tableName &&
			tbl != "main" && tbl != "local" && tbl != "default" {
			conflicting = append(conflicting, r)
		}
	}

	if len(conflicting) > 0 {
		var details []string
		for _, r := range conflicting {
			details = append(details, fmt.Sprintf("from %s lookup %s (priority %d)",
				ptrStr(r.SelectorFrom), ptrStr(r.Table), r.Priority))
		}
		results = append(results, models.ValidationResult{
			InterfaceName: iface.Name,
			CheckName:     "no_conflicting_rules",
			IsCorrect:     false,
			CurrentValue:  fmt.Sprintf("Conflicting rules: %s", strings.Join(details, ", ")),
			ExpectedValue: "No rules from this IP pointing to other tables",
			FixDescription: fmt.Sprintf(
				"Existing rules direct traffic from %s to table(s) other than '%s'. "+
					"This may conflict with SBR configuration. Review and remove "+
					"conflicting rules or use --exclude %s to skip this interface.",
				iface.IPAddress, tableName, iface.Name),
		})
	} else {
		results = append(results, models.ValidationResult{
			InterfaceName:  iface.Name,
			CheckName:      "no_conflicting_rules",
			IsCorrect:      true,
			CurrentValue:   "No conflicting rules found",
			ExpectedValue:  "No conflicting rules",
			FixDescription: "",
		})
	}

	return results
}

func validateDefaultRoute(state *models.SystemState) []models.ValidationResult {
	hasDefault := false
	for _, r := range state.RoutesMain {
		if r.Destination == "default" {
			hasDefault = true
			break
		}
	}

	fix := ""
	if !hasDefault {
		fix = "The main routing table has no default route. This means the system " +
			"has no general internet connectivity path. SBR configuration should " +
			"not remove the main table's default route."
	}

	return []models.ValidationResult{{
		InterfaceName: "(main table)",
		CheckName:     "default_route_intact",
		IsCorrect:     hasDefault,
		CurrentValue: fmt.Sprintf("Default route %s in main table",
			boolStr(hasDefault, "present", "MISSING")),
		ExpectedValue:  "Default route present in main table",
		FixDescription: fix,
	}}
}

// Helpers

func boolStr(b bool, ifTrue, ifFalse string) string {
	if b {
		return ifTrue
	}
	return ifFalse
}

func ptrStr(s *string) string {
	if s != nil {
		return *s
	}
	return "<nil>"
}

func init() {
	// Suppress unused import warning for log.
	_ = log.Println
}
