package persistence

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
)

// NetworkManagerBackend writes a NetworkManager dispatcher script for SBR
// persistence. Creates /etc/NetworkManager/dispatcher.d/50-sbr-config which
// is called by NetworkManager when interfaces come up or go down.
type NetworkManagerBackend struct{}

func (b *NetworkManagerBackend) WriteConfig(
	interfaces []models.InterfaceInfo,
	tables []models.RoutingTable,
) ([]string, error) {
	scriptPath := filepath.Join(constants.NMDispatcherDir, constants.NMDispatcherScript)

	if err := os.MkdirAll(constants.NMDispatcherDir, 0755); err != nil {
		return nil, fmt.Errorf("create NM dispatcher dir: %w", err)
	}

	script := b.generateScript(interfaces, tables)
	if err := exec.WriteFileAtomic(scriptPath, script, 0755); err != nil {
		return nil, fmt.Errorf("write NM dispatcher script: %w", err)
	}

	log.Printf("[INFO] Wrote NM dispatcher script: %s", scriptPath)
	return []string{scriptPath}, nil
}

func (b *NetworkManagerBackend) RemoveConfig() []string {
	scriptPath := filepath.Join(constants.NMDispatcherDir, constants.NMDispatcherScript)
	content, err := exec.ReadFile(scriptPath)
	if err != nil || content == "" {
		return nil
	}
	if strings.Contains(content, constants.ManagedComment) {
		os.Remove(scriptPath)
		log.Printf("[INFO] Removed NM dispatcher script: %s", scriptPath)
		return []string{scriptPath}
	}
	return nil
}

func (b *NetworkManagerBackend) Describe() string {
	scriptPath := filepath.Join(constants.NMDispatcherDir, constants.NMDispatcherScript)
	return fmt.Sprintf(
		"NetworkManager dispatcher script at %s\n"+
			"Called automatically when interfaces come up/down.", scriptPath)
}

func (b *NetworkManagerBackend) generateScript(
	interfaces []models.InterfaceInfo,
	tables []models.RoutingTable,
) string {
	// Build table name->number mapping.
	tableNum := make(map[string]int)
	for _, t := range tables {
		tableNum[t.Name] = t.Number
	}

	lines := []string{
		"#!/bin/bash",
		constants.ManagedComment,
		"# NetworkManager dispatcher script for source-based routing.",
		"# Called with $1=interface_name $2=action (up/down)",
		"",
		`IFACE="$1"`,
		`ACTION="$2"`,
		"",
		`case "$IFACE" in`,
	}

	for _, iface := range interfaces {
		tableName := constants.TableNamePrefix + iface.Name
		if _, ok := tableNum[tableName]; !ok {
			continue
		}

		// Build up commands from desired state (not delta).
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

		lines = append(lines, fmt.Sprintf("    %s)", iface.Name))
		lines = append(lines, `        if [ "$ACTION" = "up" ]; then`)
		for _, cmd := range upCmds {
			lines = append(lines, fmt.Sprintf("            %s", cmd))
		}
		lines = append(lines, `        elif [ "$ACTION" = "down" ]; then`)
		for _, cmd := range downCmds {
			lines = append(lines, fmt.Sprintf("            %s 2>/dev/null", cmd))
		}
		lines = append(lines, "        fi")
		lines = append(lines, "        ;;")
	}

	lines = append(lines, "esac")
	lines = append(lines, "")

	return strings.Join(lines, "\n")
}
