// Package sysctl validates and configures kernel sysctl parameters for
// source-based routing.
package sysctl

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
)

// ReadSysctl reads a sysctl value from /proc/sys.
func ReadSysctl(key string) string {
	procPath := "/proc/sys/" + strings.ReplaceAll(key, ".", "/")
	data, err := os.ReadFile(procPath)
	if err != nil {
		log.Printf("[WARN] Cannot read sysctl %s: %v", key, err)
		return "unknown"
	}
	return strings.TrimSpace(string(data))
}

// ReadAllSysctlValues reads all SBR-relevant sysctl values.
func ReadAllSysctlValues(interfaceNames []string) map[string]string {
	values := make(map[string]string)

	// Global settings.
	for key := range constants.SysctlSettings {
		values[key] = ReadSysctl(key)
	}

	// Per-interface rp_filter.
	for _, iface := range interfaceNames {
		key := strings.ReplaceAll(constants.SysctlPerIfaceTemplate, "{iface}", iface)
		values[key] = ReadSysctl(key)
	}

	return values
}

// ValidateSysctl validates sysctl settings against SBR requirements.
func ValidateSysctl(currentValues map[string]string, interfaceNames []string) []models.ValidationResult {
	var results []models.ValidationResult

	// Check global settings.
	for key, spec := range constants.SysctlSettings {
		current := currentValues[key]
		if current == "" {
			current = "unknown"
		}

		currentDisplay := current
		if strings.Contains(key, "rp_filter") {
			currentDisplay = fmt.Sprintf("%s (%s)", current, describeRPFilter(current))
		}

		results = append(results, models.ValidationResult{
			InterfaceName: "(global)",
			CheckName:     fmt.Sprintf("sysctl %s", key),
			IsCorrect:     current == spec.Required,
			CurrentValue:  currentDisplay,
			ExpectedValue: fmt.Sprintf("%s (%s)", spec.Required, spec.Description),
			FixDescription: func() string {
				if current != spec.Required {
					return spec.Reason
				}
				return ""
			}(),
		})
	}

	// Check per-interface rp_filter.
	for _, iface := range interfaceNames {
		key := strings.ReplaceAll(constants.SysctlPerIfaceTemplate, "{iface}", iface)
		current := currentValues[key]
		if current == "" {
			current = "unknown"
		}
		required := "2"

		results = append(results, models.ValidationResult{
			InterfaceName: iface,
			CheckName:     fmt.Sprintf("sysctl %s", key),
			IsCorrect:     current == required,
			CurrentValue:  fmt.Sprintf("%s (%s)", current, describeRPFilter(current)),
			ExpectedValue: fmt.Sprintf("%s (loose mode)", required),
			FixDescription: func() string {
				if current != required {
					return fmt.Sprintf(
						"Per-interface rp_filter for %s must be set to loose mode (2). "+
							"The kernel uses max(all, iface) so both the global and per-interface "+
							"settings must be 2 for loose mode to take effect.", iface)
				}
				return ""
			}(),
		})
	}

	return results
}

// PlanSysctlChanges generates PlannedChange entries for sysctl settings
// that need updating.
func PlanSysctlChanges(currentValues map[string]string, interfaceNames []string) []models.PlannedChange {
	var changes []models.PlannedChange

	// Global settings.
	for key, spec := range constants.SysctlSettings {
		current := currentValues[key]
		if current == "" {
			current = "unknown"
		}
		if current != spec.Required {
			change := models.PlannedChange{
				ChangeType:  models.ChangeSetSysctl,
				Description: fmt.Sprintf("Set %s = %s", key, spec.Required),
				Reason:      spec.Reason,
				Command:     fmt.Sprintf("sysctl -w %s=%s", key, spec.Required),
			}
			if current != "unknown" {
				change.RollbackCommand = models.StrPtr(fmt.Sprintf("sysctl -w %s=%s", key, current))
			}
			changes = append(changes, change)
		}
	}

	// Per-interface rp_filter.
	for _, iface := range interfaceNames {
		key := strings.ReplaceAll(constants.SysctlPerIfaceTemplate, "{iface}", iface)
		current := currentValues[key]
		if current == "" {
			current = "unknown"
		}
		required := "2"
		if current != required {
			change := models.PlannedChange{
				ChangeType: models.ChangeSetSysctl,
				Description: fmt.Sprintf("Set %s = %s", key, required),
				Reason: fmt.Sprintf(
					"Per-interface rp_filter for %s must be loose mode (2) "+
						"so that packets arriving on %s are not dropped by the "+
						"reverse path filter when the main table doesn't have a matching route.",
					iface, iface),
				Command:   fmt.Sprintf("sysctl -w %s=%s", key, required),
				Interface: models.StrPtr(iface),
			}
			if current != "unknown" {
				change.RollbackCommand = models.StrPtr(fmt.Sprintf("sysctl -w %s=%s", key, current))
			}
			changes = append(changes, change)
		}
	}

	return changes
}

// ApplySysctl applies a single sysctl setting at runtime.
func ApplySysctl(key, value string) error {
	_, err := exec.RunCommand(fmt.Sprintf("sysctl -w %s=%s", key, value), true, 10)
	if err != nil {
		return err
	}
	log.Printf("[INFO] Set sysctl %s = %s", key, value)
	return nil
}

// WriteSysctlPersistence writes /etc/sysctl.d/90-sbr-config.conf.
// The file is always generated from the COMPLETE set of desired sysctl
// settings (not from this run's delta) so it is correct even when all
// values were already set by a previous run.
func WriteSysctlPersistence(interfaceNames []string) (string, error) {
	if len(interfaceNames) == 0 {
		return "", nil
	}

	var lines []string
	lines = append(lines,
		constants.ManagedComment,
		"# Sysctl settings for source-based routing",
		"#",
		"# These settings ensure multi-NIC systems correctly handle",
		"# reverse path filtering and ARP for source-based routing.",
		"",
	)

	// Global settings — iterate in Python-compatible order for file compatibility.
	keys := constants.SysctlSettingsOrder

	for _, key := range keys {
		spec := constants.SysctlSettings[key]
		lines = append(lines,
			fmt.Sprintf("# %s", spec.Description),
			fmt.Sprintf("%s = %s", key, spec.Required),
			"",
		)
	}

	// Per-interface rp_filter.
	sorted := make([]string, len(interfaceNames))
	copy(sorted, interfaceNames)
	sort.Strings(sorted)

	for _, iface := range sorted {
		key := strings.ReplaceAll(constants.SysctlPerIfaceTemplate, "{iface}", iface)
		lines = append(lines,
			fmt.Sprintf("# Loose mode rp_filter for %s", iface),
			fmt.Sprintf("%s = 2", key),
			"",
		)
	}

	content := strings.Join(lines, "\n") + "\n"

	sysctlDir := filepath.Dir(constants.SysctlConfPath)
	if err := os.MkdirAll(sysctlDir, 0755); err != nil {
		return "", fmt.Errorf("create sysctl.d dir: %w", err)
	}

	if err := exec.WriteFileAtomic(constants.SysctlConfPath, content, 0644); err != nil {
		return "", err
	}
	log.Printf("[INFO] Wrote sysctl persistence config to %s", constants.SysctlConfPath)
	return constants.SysctlConfPath, nil
}

// RemoveSysctlPersistence removes the sbr-config sysctl.d file if it exists.
func RemoveSysctlPersistence() bool {
	content, err := exec.ReadFile(constants.SysctlConfPath)
	if err != nil || content == "" {
		return false
	}
	if !strings.Contains(content, constants.ManagedComment) {
		log.Printf("[WARN] %s exists but doesn't appear to be managed by sbr-config; skipping removal",
			constants.SysctlConfPath)
		return false
	}
	if err := os.Remove(constants.SysctlConfPath); err != nil {
		log.Printf("[WARN] Failed to remove %s: %v", constants.SysctlConfPath, err)
		return false
	}
	log.Printf("[INFO] Removed sysctl persistence config %s", constants.SysctlConfPath)
	return true
}

// describeRPFilter returns a human-readable description of an rp_filter value.
func describeRPFilter(value string) string {
	switch value {
	case "0":
		return "disabled"
	case "1":
		return "strict mode"
	case "2":
		return "loose mode"
	default:
		return fmt.Sprintf("value=%s", value)
	}
}
