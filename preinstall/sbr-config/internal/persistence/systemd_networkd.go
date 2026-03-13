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

// SystemdNetworkdBackend writes systemd-networkd .network files for SBR
// persistence. Creates /etc/systemd/network/50-sbr-<iface>.network files
// with [Route] and [RoutingPolicyRule] sections.
type SystemdNetworkdBackend struct{}

func (b *SystemdNetworkdBackend) WriteConfig(
	interfaces []models.InterfaceInfo,
	tables []models.RoutingTable,
) ([]string, error) {
	if err := os.MkdirAll(constants.SystemdNetworkDir, 0755); err != nil {
		return nil, fmt.Errorf("create systemd network dir: %w", err)
	}

	// Build table name->number mapping.
	tableNum := make(map[string]int)
	for _, t := range tables {
		tableNum[t.Name] = t.Number
	}

	var written []string
	for _, iface := range interfaces {
		tableName := constants.TableNamePrefix + iface.Name
		tnum, ok := tableNum[tableName]
		if !ok {
			continue
		}

		content := b.generateNetworkFile(iface, tnum)
		fpath := filepath.Join(constants.SystemdNetworkDir, fmt.Sprintf("50-sbr-%s.network", iface.Name))
		if err := exec.WriteFileAtomic(fpath, content, 0644); err != nil {
			return written, fmt.Errorf("write networkd config %s: %w", fpath, err)
		}
		written = append(written, fpath)
		log.Printf("[INFO] Wrote networkd config: %s", fpath)
	}

	// Reload networkd.
	if len(written) > 0 {
		exec.RunCommand("networkctl reload", false, 10)
	}

	return written, nil
}

func (b *SystemdNetworkdBackend) RemoveConfig() []string {
	var removed []string
	entries, err := os.ReadDir(constants.SystemdNetworkDir)
	if err != nil {
		return nil
	}

	for _, e := range entries {
		name := e.Name()
		if !strings.HasPrefix(name, "50-sbr-") || !strings.HasSuffix(name, ".network") {
			continue
		}
		fpath := filepath.Join(constants.SystemdNetworkDir, name)
		content, err := exec.ReadFile(fpath)
		if err != nil || content == "" {
			continue
		}
		if strings.Contains(content, constants.ManagedComment) {
			os.Remove(fpath)
			removed = append(removed, fpath)
			log.Printf("[INFO] Removed networkd config: %s", fpath)
		}
	}

	if len(removed) > 0 {
		exec.RunCommand("networkctl reload", false, 10)
	}

	return removed
}

func (b *SystemdNetworkdBackend) Describe() string {
	return fmt.Sprintf(
		"systemd-networkd .network files in %s/\n"+
			"Files named 50-sbr-<interface>.network with Route and RoutingPolicyRule sections.",
		constants.SystemdNetworkDir)
}

func (b *SystemdNetworkdBackend) generateNetworkFile(iface models.InterfaceInfo, tableNumber int) string {
	// Deterministic priority from table number (mirrors planner allocation).
	priority := constants.RulePriorityStart + (tableNumber-constants.TableNumberStart)*constants.RulePriorityIncrement

	lines := []string{
		constants.ManagedComment,
		fmt.Sprintf("# Source-based routing for %s (%s)", iface.Name, iface.IPAddress),
		"",
		"[Match]",
		fmt.Sprintf("Name=%s", iface.Name),
		"",
		"[Route]",
		fmt.Sprintf("Destination=%s", iface.Subnet),
		fmt.Sprintf("Table=%d", tableNumber),
		"",
	}

	// Only add default route if a gateway is known.
	if iface.Gateway != nil {
		lines = append(lines,
			"[Route]",
			fmt.Sprintf("Gateway=%s", *iface.Gateway),
			fmt.Sprintf("Table=%d", tableNumber),
			"",
		)
	}

	lines = append(lines,
		"[RoutingPolicyRule]",
		fmt.Sprintf("From=%s", iface.IPAddress),
		fmt.Sprintf("Table=%d", tableNumber),
		fmt.Sprintf("Priority=%d", priority),
		"",
	)

	return strings.Join(lines, "\n")
}
