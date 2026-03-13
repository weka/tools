package persistence

import (
	"log"
	"regexp"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/errors"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/sysctl"
)

var reEchoRTTable = regexp.MustCompile(`echo\s+'(\d+)\s+(\S+)'`)

// WritePersistence writes persistent configuration using the appropriate backend.
//
// Args:
//   - state: Current system state (includes network manager detection).
//   - changes: The planned changes that were applied.
//
// Returns the list of file paths that were written.
func WritePersistence(
	state *models.SystemState,
	changes []models.PlannedChange,
) ([]string, error) {
	var filesWritten []string

	// Build table list (include both existing and newly added).
	tables := make([]models.RoutingTable, len(state.RoutingTables))
	copy(tables, state.RoutingTables)

	for _, change := range changes {
		if change.ChangeType == models.ChangeAddRTTable {
			m := reEchoRTTable.FindStringSubmatch(change.Command)
			if m != nil {
				num := 0
				for _, c := range m[1] {
					num = num*10 + int(c-'0')
				}
				tables = append(tables, models.RoutingTable{
					Number: num,
					Name:   m[2],
				})
			}
		}
	}

	tableNames := make(map[string]bool)
	for _, t := range tables {
		tableNames[t.Name] = true
	}

	// Identify ALL interfaces that should have SBR persistence.
	// This includes interfaces configured in previous runs whose
	// routing is already correct (i.e. no new changes), so that
	// the persistence file is always a COMPLETE representation of
	// the desired state -- not just the delta from this run.
	var sbrInterfaces []models.InterfaceInfo
	for _, iface := range state.Interfaces {
		if iface.IsLoopback || iface.IsDefaultRouteInterface {
			continue
		}
		if !iface.IsUp {
			continue
		}
		expectedTable := constants.TableNamePrefix + iface.Name
		if tableNames[expectedTable] {
			sbrInterfaces = append(sbrInterfaces, iface)
		}
	}

	if len(sbrInterfaces) == 0 {
		log.Println("[INFO] No interface-level persistence needed")
		return filesWritten, nil
	}

	// Write sysctl persistence (derived from desired state, not changes).
	var ifaceNames []string
	for _, iface := range sbrInterfaces {
		ifaceNames = append(ifaceNames, iface.Name)
	}
	sysctlPath, err := sysctl.WriteSysctlPersistence(ifaceNames)
	if err != nil {
		log.Printf("[WARN] Failed to write sysctl persistence: %v", err)
	} else if sysctlPath != "" {
		filesWritten = append(filesWritten, sysctlPath)
	}

	// Select backend.
	backend := selectBackend(state.NetworkManager)
	if backend == nil {
		return filesWritten, errors.NewPersistenceError(
			"No persistence backend available for network manager: %s. "+
				"Runtime changes are active but will not survive reboot. "+
				"Consider creating a systemd service or cron @reboot job manually.",
			string(state.NetworkManager))
	}

	log.Printf("[INFO] Using persistence backend: %s", backend.Describe())
	backendFiles, err := backend.WriteConfig(sbrInterfaces, tables)
	if err != nil {
		return filesWritten, errors.NewPersistenceError("Backend write failed: %v", err)
	}
	filesWritten = append(filesWritten, backendFiles...)

	return filesWritten, nil
}

// selectBackend selects the appropriate persistence backend.
func selectBackend(nmType models.NetworkManagerType) Backend {
	switch nmType {
	case models.NMNetworkManager:
		return &NetworkManagerBackend{}
	case models.NMSystemdNetworkd:
		return &SystemdNetworkdBackend{}
	case models.NMIfupdown:
		return &IfupdownBackend{}
	case models.NMNetplanNetworkd:
		return &NetplanBackend{}
	case models.NMNetplanNM:
		// Netplan with NM renderer: use NM dispatcher as it's more reliable.
		log.Println("[INFO] Netplan with NetworkManager renderer detected. " +
			"Using NM dispatcher for persistence (more reliable than netplan routing-policy with NM).")
		return &NetworkManagerBackend{}
	default:
		return nil
	}
}
