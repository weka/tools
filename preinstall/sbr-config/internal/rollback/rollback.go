// Package rollback saves and restores system state for rollback capability.
package rollback

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/errors"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/sysctl"
)

// SaveState serializes and saves the current system state for later rollback.
// Returns the path to the saved backup file.
func SaveState(state *models.SystemState) (string, error) {
	return SaveStateToDir(state, constants.BackupDir)
}

// SaveStateToDir saves state to a specific backup directory.
func SaveStateToDir(state *models.SystemState, backupDir string) (string, error) {
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		return "", fmt.Errorf("create backup dir: %w", err)
	}

	timestamp := time.Now().UTC().Format("20060102_150405")
	fpath := filepath.Join(backupDir, fmt.Sprintf("state_%s.json", timestamp))

	// Build the JSON structure manually for backward compat with Python format.
	data := stateToMap(state)

	// Add raw file contents for exact restoration.
	data["_raw_files"] = map[string]string{
		constants.RTTablesPath: state.RTTablesFileContent,
	}

	jsonData, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal state: %w", err)
	}

	if err := os.WriteFile(fpath, jsonData, 0644); err != nil {
		return "", fmt.Errorf("write backup file: %w", err)
	}

	// Create/update "latest" symlink.
	latest := filepath.Join(backupDir, "latest.json")
	os.Remove(latest) // remove old symlink or file
	os.Symlink(fpath, latest)

	log.Printf("[INFO] Saved state backup to %s", fpath)
	return fpath, nil
}

// Rollback restores system to a previously saved state.
// If backupPath is "", uses the latest backup.
func Rollback(backupPath string) error {
	return RollbackFromDir(backupPath, constants.BackupDir)
}

// RollbackFromDir restores from a backup in a specific directory.
func RollbackFromDir(backupPath, backupDir string) error {
	if backupPath == "" {
		backupPath = filepath.Join(backupDir, "latest.json")
	}

	if _, err := os.Stat(backupPath); os.IsNotExist(err) {
		return errors.NewRollbackError(
			"No backup found at %s. Run 'sbr-config --configure' first to create a backup.",
			backupPath)
	}

	log.Printf("[INFO] Restoring from backup: %s", backupPath)

	data, err := os.ReadFile(backupPath)
	if err != nil {
		return errors.NewRollbackError("Failed to read backup file: %v", err)
	}

	var saved map[string]interface{}
	if err := json.Unmarshal(data, &saved); err != nil {
		return errors.NewRollbackError("Failed to parse backup file: %v", err)
	}

	// Step 1: Remove IP rules pointing to sbr_* tables.
	removeSBRRules()

	// Step 2: Flush custom SBR routing tables.
	flushSBRTables()

	// Step 3: Restore /etc/iproute2/rt_tables.
	restoreRTTables(saved)

	// Step 4: Restore sysctl settings.
	restoreSysctl(saved)

	// Step 5: Remove persistence configs.
	removePersistenceFiles()

	log.Println("[INFO] Rollback complete")
	return nil
}

// BackupInfo contains metadata about a backup file.
type BackupInfo struct {
	Path      string `json:"path"`
	Timestamp string `json:"timestamp"`
	IsLatest  bool   `json:"is_latest"`
}

// ListBackups lists available backup files with metadata.
func ListBackups() []BackupInfo {
	return ListBackupsFromDir(constants.BackupDir)
}

// ListBackupsFromDir lists backups from a specific directory.
func ListBackupsFromDir(backupDir string) []BackupInfo {
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		return nil
	}

	latestLink := filepath.Join(backupDir, "latest.json")
	latestTarget, _ := filepath.EvalSymlinks(latestLink)

	var backups []BackupInfo
	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasPrefix(name, "state_") || !strings.HasSuffix(name, ".json") {
			continue
		}
		fpath := filepath.Join(backupDir, name)
		realPath, _ := filepath.EvalSymlinks(fpath)

		ts := "unknown"
		data, err := os.ReadFile(fpath)
		if err == nil {
			var parsed map[string]interface{}
			if json.Unmarshal(data, &parsed) == nil {
				if t, ok := parsed["timestamp"].(string); ok {
					ts = t
				}
			}
		} else {
			ts = "unreadable"
		}

		backups = append(backups, BackupInfo{
			Path:      fpath,
			Timestamp: ts,
			IsLatest:  realPath == latestTarget,
		})
	}

	return backups
}

// PruneBackups removes old backups, keeping the most recent ones.
// Returns the number of backups removed.
func PruneBackups(keep int) int {
	return PruneBackupsFromDir(constants.BackupDir, keep)
}

// PruneBackupsFromDir prunes from a specific directory.
func PruneBackupsFromDir(backupDir string, keep int) int {
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		return 0
	}

	var files []string
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), "state_") && strings.HasSuffix(e.Name(), ".json") {
			files = append(files, e.Name())
		}
	}
	sort.Strings(files)

	if len(files) <= keep {
		return 0
	}

	toRemove := files[:len(files)-keep]
	removed := 0
	for _, fname := range toRemove {
		fpath := filepath.Join(backupDir, fname)
		if err := os.Remove(fpath); err != nil {
			log.Printf("[WARN] Failed to remove backup %s: %v", fpath, err)
		} else {
			removed++
			log.Printf("[DEBUG] Pruned old backup: %s", fpath)
		}
	}
	return removed
}

// -----------------------------------------------------------------------
// Internal rollback steps
// -----------------------------------------------------------------------

func removeSBRRules() {
	res, _ := exec.RunCommand("ip rule show", false, 10)
	for _, line := range strings.Split(res.Stdout, "\n") {
		if !strings.Contains(line, constants.TableNamePrefix) {
			continue
		}
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		ruleSpec := strings.TrimSpace(parts[1])
		ruleSpec = strings.ReplaceAll(ruleSpec, "lookup ", "table ")
		exec.RunCommand(fmt.Sprintf("ip rule del %s", ruleSpec), false, 10)
		log.Printf("[INFO] Removed rule: %s", ruleSpec)
	}
}

func flushSBRTables() {
	content, _ := exec.ReadFile(constants.RTTablesPath)
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#") || line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.HasPrefix(fields[1], constants.TableNamePrefix) {
			tableName := fields[1]
			exec.RunCommand(fmt.Sprintf("ip route flush table %s", tableName), false, 10)
			log.Printf("[INFO] Flushed table: %s", tableName)
		}
	}
}

func restoreRTTables(saved map[string]interface{}) {
	rawFiles, _ := saved["_raw_files"].(map[string]interface{})
	if rawFiles == nil {
		removeRTTablesSBREntries()
		return
	}

	originalContent, ok := rawFiles[constants.RTTablesPath].(string)
	if ok && originalContent != "" {
		exec.WriteFileAtomic(constants.RTTablesPath, originalContent, 0644)
		log.Printf("[INFO] Restored %s from backup", constants.RTTablesPath)
	} else {
		removeRTTablesSBREntries()
	}
}

func removeRTTablesSBREntries() {
	content, _ := exec.ReadFile(constants.RTTablesPath)
	var newLines []string
	for _, line := range strings.Split(content, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed != "" && !strings.HasPrefix(trimmed, "#") && strings.Contains(line, constants.TableNamePrefix) {
			continue
		}
		if trimmed == constants.ManagedComment {
			continue
		}
		newLines = append(newLines, line)
	}
	result := strings.Join(newLines, "\n")
	if !strings.HasSuffix(result, "\n") {
		result += "\n"
	}
	exec.WriteFileAtomic(constants.RTTablesPath, result, 0644)
	log.Printf("[INFO] Removed sbr_ entries from %s", constants.RTTablesPath)
}

func restoreSysctl(saved map[string]interface{}) {
	savedValues, _ := saved["sysctl_values"].(map[string]interface{})
	for key, val := range savedValues {
		value, ok := val.(string)
		if !ok || value == "" || value == "unknown" {
			continue
		}
		exec.RunCommand(fmt.Sprintf("sysctl -w %s=%s", key, value), false, 10)
		log.Printf("[INFO] Restored sysctl %s = %s", key, value)
	}
	sysctl.RemoveSysctlPersistence()
}

func removePersistenceFiles() {
	// NetworkManager dispatcher script.
	nmPath := filepath.Join(constants.NMDispatcherDir, constants.NMDispatcherScript)
	removeManagedFile(nmPath)

	// Netplan config.
	netplanPath := filepath.Join(constants.NetplanDir, constants.NetplanConfigFile)
	if removeManagedFile(netplanPath) {
		exec.RunCommand("netplan apply", false, 10)
	}

	// systemd-networkd drop-in files.
	entries, err := os.ReadDir(constants.SystemdNetworkDir)
	if err == nil {
		for _, e := range entries {
			if strings.HasPrefix(e.Name(), "50-sbr-") {
				removeManagedFile(filepath.Join(constants.SystemdNetworkDir, e.Name()))
			}
		}
	}

	// ifupdown files in interfaces.d.
	entries, err = os.ReadDir(constants.InterfacesDDir)
	if err == nil {
		for _, e := range entries {
			if strings.HasPrefix(e.Name(), "sbr-") {
				removeManagedFile(filepath.Join(constants.InterfacesDDir, e.Name()))
			}
		}
	}

	// Sysctl persistence.
	sysctl.RemoveSysctlPersistence()
}

func removeManagedFile(path string) bool {
	content, err := exec.ReadFile(path)
	if err != nil || content == "" {
		return false
	}
	if strings.Contains(content, constants.ManagedComment) {
		os.Remove(path)
		log.Printf("[INFO] Removed managed file: %s", path)
		return true
	}
	log.Printf("[WARN] File %s exists but doesn't appear managed by sbr-config; skipping", path)
	return false
}

// -----------------------------------------------------------------------
// State serialization helpers (for backward compatibility with Python format)
// -----------------------------------------------------------------------

// We need models imported — add an alias to avoid circular imports.
// The models package is imported by the caller.

func stateToMap(state *models.SystemState) map[string]interface{} {
	m := make(map[string]interface{})

	// Interfaces.
	var ifaces []map[string]interface{}
	for _, i := range state.Interfaces {
		im := map[string]interface{}{
			"name":                       i.Name,
			"ip_address":                 i.IPAddress,
			"prefix_length":              i.PrefixLength,
			"subnet":                     i.Subnet,
			"gateway":                    i.Gateway,
			"mac_address":                i.MACAddress,
			"is_up":                      i.IsUp,
			"is_loopback":                i.IsLoopback,
			"is_default_route_interface": i.IsDefaultRouteInterface,
			"mtu":                        i.MTU,
		}
		ifaces = append(ifaces, im)
	}
	m["interfaces"] = ifaces

	// Routing tables.
	var tables []map[string]interface{}
	for _, t := range state.RoutingTables {
		tables = append(tables, map[string]interface{}{
			"number": t.Number,
			"name":   t.Name,
		})
	}
	m["routing_tables"] = tables

	// Routes main.
	m["routes_main"] = routesToMaps(state.RoutesMain)

	// Routes by table.
	rbt := make(map[string]interface{})
	for k, v := range state.RoutesByTable {
		rbt[k] = routesToMaps(v)
	}
	m["routes_by_table"] = rbt

	// Rules.
	var rules []map[string]interface{}
	for _, r := range state.Rules {
		rules = append(rules, map[string]interface{}{
			"priority":      r.Priority,
			"selector_from": r.SelectorFrom,
			"selector_to":   r.SelectorTo,
			"table":         r.Table,
			"iif":           r.IIF,
			"fwmark":        r.FWMark,
		})
	}
	m["rules"] = rules

	m["rt_tables_file_content"] = state.RTTablesFileContent
	m["sysctl_values"] = state.SysctlValues
	m["network_manager"] = string(state.NetworkManager)
	m["timestamp"] = state.Timestamp

	return m
}

func routesToMaps(routes []models.Route) []map[string]interface{} {
	var result []map[string]interface{}
	for _, r := range routes {
		result = append(result, map[string]interface{}{
			"destination": r.Destination,
			"gateway":     r.Gateway,
			"device":      r.Device,
			"source":      r.Source,
			"table":       r.Table,
			"metric":      r.Metric,
			"scope":       r.Scope,
			"protocol":    r.Protocol,
		})
	}
	return result
}
