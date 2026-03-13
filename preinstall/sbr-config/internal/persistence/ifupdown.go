package persistence

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
)

// IfupdownBackend writes ifupdown configuration for SBR persistence.
// Adds post-up/pre-down lines to interface stanzas in
// /etc/network/interfaces or creates drop-in files in
// /etc/network/interfaces.d/.
type IfupdownBackend struct{}

func (b *IfupdownBackend) WriteConfig(
	interfaces []models.InterfaceInfo,
	tables []models.RoutingTable,
) ([]string, error) {
	tableNum := make(map[string]int)
	for _, t := range tables {
		tableNum[t.Name] = t.Number
	}

	var written []string
	for _, iface := range interfaces {
		tableName := constants.TableNamePrefix + iface.Name
		if _, ok := tableNum[tableName]; !ok {
			continue
		}

		// Build command sets from desired state (not delta).
		upCmds := []string{
			fmt.Sprintf("ip route replace %s dev %s src %s table %s",
				iface.Subnet, iface.Name, iface.IPAddress, tableName),
		}
		if iface.Gateway != nil {
			upCmds = append(upCmds, fmt.Sprintf(
				"ip route replace default via %s dev %s table %s",
				*iface.Gateway, iface.Name, tableName))
		}
		upCmds = append(upCmds, fmt.Sprintf(
			"ip rule add from %s table %s 2>/dev/null",
			iface.IPAddress, tableName))

		downCmds := []string{
			fmt.Sprintf("ip rule del from %s table %s", iface.IPAddress, tableName),
			fmt.Sprintf("ip route flush table %s", tableName),
		}

		// Try to add to existing stanza in interfaces file.
		if b.addToInterfacesFile(iface.Name, upCmds, downCmds) {
			written = append(written, constants.InterfacesFile)
			continue
		}

		// Fall back to drop-in file.
		fpath, err := b.writeDropin(iface, upCmds, downCmds)
		if err != nil {
			log.Printf("[WARN] Failed to write ifupdown drop-in for %s: %v", iface.Name, err)
			continue
		}
		if fpath != "" {
			written = append(written, fpath)
		}
	}

	return written, nil
}

func (b *IfupdownBackend) RemoveConfig() []string {
	var removed []string

	// Remove from interfaces file.
	content, err := exec.ReadFile(constants.InterfacesFile)
	if err == nil && content != "" && strings.Contains(content, constants.ManagedComment) {
		cleaned := removeManagedLines(content)
		if cleaned != content {
			exec.WriteFileAtomic(constants.InterfacesFile, cleaned, 0644)
			removed = append(removed, constants.InterfacesFile)
		}
	}

	// Remove drop-in files.
	entries, err := os.ReadDir(constants.InterfacesDDir)
	if err == nil {
		for _, e := range entries {
			if !strings.HasPrefix(e.Name(), "sbr-") {
				continue
			}
			fpath := filepath.Join(constants.InterfacesDDir, e.Name())
			fc, err := exec.ReadFile(fpath)
			if err != nil || fc == "" {
				continue
			}
			if strings.Contains(fc, constants.ManagedComment) {
				os.Remove(fpath)
				removed = append(removed, fpath)
			}
		}
	}

	return removed
}

func (b *IfupdownBackend) Describe() string {
	return fmt.Sprintf(
		"ifupdown configuration:\n"+
			"  post-up/pre-down lines in %s\n"+
			"  or drop-in files in %s/",
		constants.InterfacesFile, constants.InterfacesDDir)
}

// addToInterfacesFile tries to add post-up/pre-down lines to an existing
// stanza. If managed lines from a previous run already exist, they are
// removed first to avoid accumulating duplicate entries.
// Returns true if successful, false if the stanza wasn't found.
func (b *IfupdownBackend) addToInterfacesFile(
	ifaceName string,
	upCmds, downCmds []string,
) bool {
	content, err := exec.ReadFile(constants.InterfacesFile)
	if err != nil || content == "" {
		return false
	}

	// Remove any existing managed lines first to prevent duplicates.
	if strings.Contains(content, constants.ManagedComment) {
		content = removeManagedLines(content)
	}

	// Find the stanza for this interface.
	pattern := regexp.MustCompile(
		`(?m)^(iface\s+` + regexp.QuoteMeta(ifaceName) + `\s+.*?)` +
			`(?=\niface\s|\nauto\s|\nallow-|\nsource\s|\nmapping\s|\n\z|\z)`)
	loc := pattern.FindStringIndex(content)
	if loc == nil {
		return false
	}
	stanzaEnd := loc[1]

	// Build lines to insert.
	var insertLines []string
	insertLines = append(insertLines, fmt.Sprintf("    %s", constants.ManagedComment))
	for _, cmd := range upCmds {
		insertLines = append(insertLines, fmt.Sprintf("    post-up %s", cmd))
	}
	// Down commands in reverse order.
	for i := len(downCmds) - 1; i >= 0; i-- {
		insertLines = append(insertLines,
			fmt.Sprintf("    pre-down %s 2>/dev/null || true", downCmds[i]))
	}
	insertBlock := strings.Join(insertLines, "\n")

	// Insert at end of stanza.
	newContent := content[:stanzaEnd] + "\n" + insertBlock + content[stanzaEnd:]
	exec.WriteFileAtomic(constants.InterfacesFile, newContent, 0644)
	log.Printf("[INFO] Added SBR lines to %s stanza in %s", ifaceName, constants.InterfacesFile)
	return true
}

// writeDropin writes a drop-in file in /etc/network/interfaces.d/.
func (b *IfupdownBackend) writeDropin(
	iface models.InterfaceInfo,
	upCmds, downCmds []string,
) (string, error) {
	if err := os.MkdirAll(constants.InterfacesDDir, 0755); err != nil {
		return "", fmt.Errorf("create interfaces.d dir: %w", err)
	}

	// Check that interfaces file sources the directory.
	mainContent, _ := exec.ReadFile(constants.InterfacesFile)
	if !strings.Contains(mainContent, "source") && !strings.Contains(mainContent, "interfaces.d") {
		log.Printf("[WARN] %s does not source %s -- drop-in may not be loaded",
			constants.InterfacesFile, constants.InterfacesDDir)
	}

	fpath := filepath.Join(constants.InterfacesDDir, fmt.Sprintf("sbr-%s", iface.Name))

	// Do NOT redefine the interface -- that would conflict with the main
	// stanza. Just add hook commands.
	lines := []string{
		constants.ManagedComment,
		fmt.Sprintf("# Source-based routing hooks for %s (%s)", iface.Name, iface.IPAddress),
		"",
	}
	for _, cmd := range upCmds {
		lines = append(lines, fmt.Sprintf("post-up %s", cmd))
	}
	// Down commands in reverse order.
	for i := len(downCmds) - 1; i >= 0; i-- {
		lines = append(lines, fmt.Sprintf("pre-down %s 2>/dev/null || true", downCmds[i]))
	}
	lines = append(lines, "")

	if err := exec.WriteFileAtomic(fpath, strings.Join(lines, "\n"), 0644); err != nil {
		return "", err
	}
	log.Printf("[INFO] Wrote ifupdown drop-in: %s", fpath)
	return fpath, nil
}

// removeManagedLines removes lines between MANAGED_COMMENT markers.
func removeManagedLines(content string) string {
	lines := strings.Split(content, "\n")
	var newLines []string
	inManagedBlock := false

	for _, line := range lines {
		if strings.Contains(line, constants.ManagedComment) {
			inManagedBlock = true
			continue
		}
		if inManagedBlock {
			trimmed := strings.TrimSpace(line)
			if strings.HasPrefix(trimmed, "post-up") || strings.HasPrefix(trimmed, "pre-down") {
				continue
			}
			inManagedBlock = false
		}
		newLines = append(newLines, line)
	}

	result := strings.Join(newLines, "\n")
	if strings.HasSuffix(content, "\n") && !strings.HasSuffix(result, "\n") {
		result += "\n"
	}
	return result
}
