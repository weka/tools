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

// NetplanBackend writes Netplan YAML configuration for SBR persistence.
// Creates /etc/netplan/90-sbr-config.yaml with routing-policy sections
// for each interface.
type NetplanBackend struct{}

func (b *NetplanBackend) WriteConfig(
	interfaces []models.InterfaceInfo,
	tables []models.RoutingTable,
) ([]string, error) {
	if err := os.MkdirAll(constants.NetplanDir, 0755); err != nil {
		return nil, fmt.Errorf("create netplan dir: %w", err)
	}

	// Build table name->number mapping.
	tableNum := make(map[string]int)
	for _, t := range tables {
		tableNum[t.Name] = t.Number
	}

	content := b.generateYAML(interfaces, tableNum)
	fpath := filepath.Join(constants.NetplanDir, constants.NetplanConfigFile)
	if err := exec.WriteFileAtomic(fpath, content, 0644); err != nil {
		return nil, fmt.Errorf("write netplan config: %w", err)
	}

	log.Printf("[INFO] Wrote netplan config: %s", fpath)

	// Apply netplan.
	exec.RunCommand("netplan apply", false, 10)

	return []string{fpath}, nil
}

func (b *NetplanBackend) RemoveConfig() []string {
	fpath := filepath.Join(constants.NetplanDir, constants.NetplanConfigFile)
	content, err := exec.ReadFile(fpath)
	if err != nil || content == "" {
		return nil
	}
	if strings.Contains(content, constants.ManagedComment) {
		os.Remove(fpath)
		log.Printf("[INFO] Removed netplan config: %s", fpath)
		exec.RunCommand("netplan apply", false, 10)
		return []string{fpath}
	}
	return nil
}

func (b *NetplanBackend) Describe() string {
	fpath := filepath.Join(constants.NetplanDir, constants.NetplanConfigFile)
	return fmt.Sprintf(
		"Netplan YAML config at %s\n"+
			"Contains routing-policy rules for each SBR interface.", fpath)
}

func (b *NetplanBackend) generateYAML(
	interfaces []models.InterfaceInfo,
	tableNum map[string]int,
) string {
	// Write YAML manually to avoid requiring a YAML library.
	lines := []string{
		constants.ManagedComment,
		"# Source-based routing configuration for multi-NIC systems.",
		"# This file is merged with other netplan configs.",
		"",
		"network:",
		"  version: 2",
		"  ethernets:",
	}

	for _, iface := range interfaces {
		tableName := constants.TableNamePrefix + iface.Name
		tnum, ok := tableNum[tableName]
		if !ok {
			continue
		}

		priority := constants.RulePriorityStart + (tnum-constants.TableNumberStart)*constants.RulePriorityIncrement

		routeLines := []string{
			fmt.Sprintf("    %s:", iface.Name),
			"      routes:",
			fmt.Sprintf("        - to: %s", iface.Subnet),
			fmt.Sprintf("          table: %d", tnum),
		}

		// Only add default route if a gateway is known.
		if iface.Gateway != nil {
			routeLines = append(routeLines,
				"        - to: default",
				fmt.Sprintf("          via: %s", *iface.Gateway),
				fmt.Sprintf("          table: %d", tnum),
			)
		}

		routeLines = append(routeLines,
			"      routing-policy:",
			fmt.Sprintf("        - from: %s", iface.IPAddress),
			fmt.Sprintf("          table: %d", tnum),
			fmt.Sprintf("          priority: %d", priority),
		)

		lines = append(lines, routeLines...)
	}

	lines = append(lines, "")
	return strings.Join(lines, "\n")
}
