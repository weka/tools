// Package configurator executes planned changes with atomic rollback on failure.
package configurator

import (
	"fmt"
	"log"
	"regexp"
	"strings"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/errors"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/sysctl"
)

var reRTTableEntry = regexp.MustCompile(`echo\s+'(\d+\s+\S+)'`)

// ApplyChanges applies a list of planned changes to the system.
// If any change fails, all previously applied changes are rolled back.
// Returns the number of changes successfully applied.
func ApplyChanges(changes []models.PlannedChange) (int, error) {
	if len(changes) == 0 {
		log.Println("[INFO] No changes to apply")
		return 0, nil
	}

	var applied []models.PlannedChange

	for _, change := range changes {
		log.Printf("[INFO] Applying: %s", change.Description)
		if err := executeChange(&change); err != nil {
			log.Printf("[ERROR] Failed at: %s -- %v", change.Description, err)
			log.Printf("[INFO] Rolling back %d applied changes", len(applied))
			rollbackApplied(applied)
			return len(applied), errors.NewConfigurationError(
				"Failed to apply: %s\nError: %v\nRolled back %d previously applied changes.",
				change.Description, err, len(applied))
		}
		applied = append(applied, change)
		log.Printf("[INFO] Applied: %s", change.Description)
	}

	log.Printf("[INFO] Successfully applied %d changes", len(applied))
	return len(applied), nil
}

func executeChange(change *models.PlannedChange) error {
	switch change.ChangeType {
	case models.ChangeAddRTTable:
		return addRTTableEntry(change)

	case models.ChangeSetSysctl:
		// Extract key=value from "sysctl -w key=value".
		kv := strings.TrimPrefix(change.Command, "sysctl -w ")
		parts := strings.SplitN(kv, "=", 2)
		if len(parts) != 2 {
			return errors.NewConfigurationError("Cannot parse sysctl command: %s", change.Command)
		}
		return sysctl.ApplySysctl(parts[0], parts[1])

	case models.ChangeAddRoute, models.ChangeAddRule,
		models.ChangeDelRoute, models.ChangeDelRule:
		_, err := exec.RunCommand(change.Command, true, 10)
		return err

	default:
		return errors.NewConfigurationError("Unknown change type: %s", change.ChangeType)
	}
}

func addRTTableEntry(change *models.PlannedChange) error {
	content, _ := exec.ReadFile(constants.RTTablesPath)

	// Extract "NUMBER NAME" from the echo command.
	m := reRTTableEntry.FindStringSubmatch(change.Command)
	if m == nil {
		return errors.NewConfigurationError(
			"Cannot parse rt_table entry from command: %s", change.Command)
	}
	entry := m[1]

	// Check if already present (idempotent).
	if strings.Contains(content, entry) {
		log.Printf("[INFO] rt_tables entry already present: %s", entry)
		return nil
	}

	// Ensure the file ends with a newline before appending.
	if content != "" && !strings.HasSuffix(content, "\n") {
		content += "\n"
	}

	// Add our marker if not present.
	if !strings.Contains(content, constants.ManagedComment) {
		content += "\n" + constants.ManagedComment + "\n"
	}

	content += entry + "\n"
	return exec.WriteFileAtomic(constants.RTTablesPath, content, 0644)
}

func rollbackApplied(applied []models.PlannedChange) {
	// Reverse order.
	for i := len(applied) - 1; i >= 0; i-- {
		change := applied[i]
		switch change.ChangeType {
		case models.ChangeAddRTTable:
			if err := removeRTTableEntry(&change); err != nil {
				log.Printf("[ERROR] Rollback failed for rt_table: %v", err)
			}
		case models.ChangeSetSysctl:
			if change.RollbackCommand != nil {
				exec.RunCommand(*change.RollbackCommand, false, 10)
			}
		default:
			if change.RollbackCommand != nil {
				if _, err := exec.RunCommand(*change.RollbackCommand, false, 10); err != nil {
					log.Printf("[ERROR] Rollback failed: %s -- %v", *change.RollbackCommand, err)
				}
			} else {
				log.Printf("[WARN] No rollback command for: %s", change.Description)
			}
		}
	}
}

func removeRTTableEntry(change *models.PlannedChange) error {
	m := reRTTableEntry.FindStringSubmatch(change.Command)
	if m == nil {
		return nil
	}
	entry := m[1]

	content, _ := exec.ReadFile(constants.RTTablesPath)
	lines := strings.Split(content, "\n")
	var newLines []string
	for _, line := range lines {
		if strings.TrimSpace(line) != entry {
			newLines = append(newLines, line)
		}
	}

	// Remove our marker if no sbr_ entries remain.
	hasSBR := false
	for _, line := range newLines {
		if !strings.HasPrefix(strings.TrimSpace(line), "#") && strings.Contains(line, "sbr_") {
			hasSBR = true
			break
		}
	}
	if !hasSBR {
		var cleaned []string
		for _, line := range newLines {
			if strings.TrimSpace(line) != constants.ManagedComment {
				cleaned = append(cleaned, line)
			}
		}
		newLines = cleaned
	}

	result := strings.Join(newLines, "\n")
	if !strings.HasSuffix(result, "\n") {
		result += "\n"
	}
	return exec.WriteFileAtomic(constants.RTTablesPath, result, 0644)
}

// RollbackApplied is exported for use by the CLI dead-man's-switch.
func RollbackApplied(applied []models.PlannedChange) {
	rollbackApplied(applied)
}

// FormatRTTableCommand creates a formatted command to add an rt_table entry.
func FormatRTTableCommand(number int, name string) string {
	return fmt.Sprintf("echo '%d %s' >> /etc/iproute2/rt_tables", number, name)
}
