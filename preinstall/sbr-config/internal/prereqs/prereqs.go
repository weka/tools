// Package prereqs replaces the bash wrapper's prerequisite checks.
// It validates OS, tools, root, files, and network interfaces.
package prereqs

import (
	"fmt"
	"os"
	osExec "os/exec"
	"runtime"
	"strings"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/output"
)

// CheckResult holds one prerequisite check result.
type CheckResult struct {
	Level   string // "PASS", "FAIL", "WARN", "INFO"
	Message string
}

// CheckPrereqs runs all prerequisite checks and prints the results.
// Returns exit code 0 if all required checks pass, 1 if any fail.
func CheckPrereqs(out *output.Output) int {
	out.NL()
	out.Info("sbr-config: Prerequisite Check")
	out.Info("==============================")
	out.NL()

	var results []CheckResult

	// --- Required ---
	out.Info("Required:")
	out.Info("  -------")

	// OS check.
	if runtime.GOOS == "linux" {
		distro := detectDistro()
		extra := ""
		if distro != "" {
			extra = fmt.Sprintf(" (%s)", distro)
		}
		res, _ := exec.RunCommand("uname -r", false, 5)
		kernel := strings.TrimSpace(res.Stdout)
		results = append(results, pass(fmt.Sprintf("Linux OS: %s%s", kernel, extra)))
	} else {
		results = append(results, fail(fmt.Sprintf("Linux OS required (detected: %s)", runtime.GOOS)))
	}

	// iproute2.
	if exec.CommandExists("ip") {
		res, _ := exec.RunCommand("ip -V", false, 5)
		ver := strings.TrimSpace(res.Stdout)
		if ver == "" {
			ver = strings.TrimSpace(res.Stderr)
		}
		results = append(results, pass(fmt.Sprintf("iproute2: %s", ver)))

		// JSON mode check.
		if exec.IPJSONSupported() {
			results = append(results, pass("iproute2 JSON mode (-j): supported"))
		} else {
			results = append(results, warn("iproute2 JSON mode (-j): not supported (will use text parsing fallback)"))
		}
	} else {
		results = append(results, fail("iproute2 (ip command) not found -- install iproute2 package"))
	}

	// sysctl.
	if exec.CommandExists("sysctl") {
		path, _ := osExec.LookPath("sysctl")
		results = append(results, pass(fmt.Sprintf("sysctl: %s", path)))
	} else {
		results = append(results, fail("sysctl not found -- install procps package"))
	}

	// Root privileges.
	if os.Geteuid() == 0 {
		results = append(results, pass("Root privileges: running as root (UID 0)"))
	} else {
		results = append(results, warn("Root privileges: not running as root (required for --configure and --rollback)"))
	}

	// /etc/iproute2/rt_tables.
	if _, err := os.Stat(constants.RTTablesPath); err == nil {
		results = append(results, pass("/etc/iproute2/rt_tables: exists"))
		// Check writable (only meaningful if root).
		f, err := os.OpenFile(constants.RTTablesPath, os.O_WRONLY, 0)
		if err == nil {
			f.Close()
			results = append(results, pass("/etc/iproute2/rt_tables: writable"))
		} else if os.Geteuid() == 0 {
			results = append(results, warn("/etc/iproute2/rt_tables: not writable"))
		} else {
			results = append(results, warn("/etc/iproute2/rt_tables: not writable (need root)"))
		}
	} else {
		results = append(results, fail("/etc/iproute2/rt_tables: not found"))
	}

	// Print required results.
	for _, r := range results {
		printResult(out, r)
	}

	// --- Network interfaces ---
	out.NL()
	out.Info("Network Interfaces:")
	out.Info("  ------------------")

	var ifaceResults []CheckResult
	ifaceCount := 0
	if exec.CommandExists("ip") {
		res, _ := exec.RunCommand("ip -o link show up", false, 10)
		for _, line := range strings.Split(res.Stdout, "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			fields := strings.Fields(line)
			if len(fields) < 2 {
				continue
			}
			name := strings.TrimRight(fields[1], ":")
			if name == "lo" {
				continue
			}
			ifaceCount++

			// Get IP if possible.
			ipRes, _ := exec.RunCommand(fmt.Sprintf("ip -4 addr show %s", name), false, 5)
			ip := ""
			for _, ipLine := range strings.Split(ipRes.Stdout, "\n") {
				ipLine = strings.TrimSpace(ipLine)
				if strings.HasPrefix(ipLine, "inet ") {
					fields := strings.Fields(ipLine)
					if len(fields) >= 2 {
						ip = fields[1]
					}
					break
				}
			}
			if ip != "" {
				ifaceResults = append(ifaceResults, info(fmt.Sprintf("%s: %s", name, ip)))
			} else {
				ifaceResults = append(ifaceResults, info(fmt.Sprintf("%s: no IPv4 address", name)))
			}
		}
	}

	for _, r := range ifaceResults {
		printResult(out, r)
	}
	out.NL()

	if ifaceCount >= 2 {
		r := pass(fmt.Sprintf("Multiple interfaces detected (%d) -- SBR is applicable", ifaceCount))
		results = append(results, r)
		printResult(out, r)
	} else if ifaceCount == 1 {
		r := warn("Only 1 non-loopback interface -- SBR requires 2+ interfaces")
		results = append(results, r)
		printResult(out, r)
	} else {
		r := warn("No active non-loopback interfaces found")
		results = append(results, r)
		printResult(out, r)
	}

	// --- Persistence backends ---
	out.NL()
	out.Info("Persistence Backends (optional, for --persist):")
	out.Info("  ------------------------------------------------")

	var persResults []CheckResult

	// NetworkManager.
	if exec.CommandExists("nmcli") {
		res, _ := exec.RunCommand("systemctl is-active NetworkManager.service", false, 5)
		status := strings.TrimSpace(res.Stdout)
		if status == "" {
			status = "inactive"
		}
		if status == "active" {
			persResults = append(persResults, pass("NetworkManager: active"))
		} else {
			persResults = append(persResults, info(fmt.Sprintf("NetworkManager: installed but %s", status)))
		}
	} else {
		persResults = append(persResults, info("NetworkManager: not installed"))
	}

	// systemd-networkd.
	res, _ := exec.RunCommand("systemctl is-active systemd-networkd.service", false, 5)
	networkdStatus := strings.TrimSpace(res.Stdout)
	if networkdStatus == "" {
		networkdStatus = "inactive"
	}
	if networkdStatus == "active" {
		persResults = append(persResults, pass("systemd-networkd: active"))
	} else {
		persResults = append(persResults, info(fmt.Sprintf("systemd-networkd: %s", networkdStatus)))
	}

	// netplan.
	if exec.CommandExists("netplan") {
		path, _ := osExec.LookPath("netplan")
		persResults = append(persResults, pass(fmt.Sprintf("netplan: %s", path)))
	} else {
		persResults = append(persResults, info("netplan: not installed"))
	}

	// ifupdown.
	if exec.CommandExists("ifup") || exec.CommandExists("ifdown") {
		if _, err := os.Stat(constants.InterfacesFile); err == nil {
			persResults = append(persResults, pass("ifupdown: available (/etc/network/interfaces exists)"))
		} else {
			persResults = append(persResults, info("ifupdown: commands found but /etc/network/interfaces missing"))
		}
	} else {
		persResults = append(persResults, info("ifupdown: not installed"))
	}

	for _, r := range persResults {
		printResult(out, r)
	}

	// --- Summary ---
	passCount := 0
	failCount := 0
	warnCount := 0
	for _, r := range results {
		switch r.Level {
		case "PASS":
			passCount++
		case "FAIL":
			failCount++
		case "WARN":
			warnCount++
		}
	}

	total := passCount + failCount + warnCount
	out.NL()
	out.Info("  ==============================")
	out.Info(fmt.Sprintf("  Summary: %d passed, %d failed, %d warnings (of %d checks)",
		passCount, failCount, warnCount, total))

	if failCount > 0 {
		out.NL()
		out.Info("  Some required prerequisites are missing. Install them before using sbr-config.")
		return 1
	}
	out.NL()
	out.Info("  All required prerequisites are met. Ready to use sbr-config.")
	return 0
}

// detectDistro reads /etc/os-release for a distro name.
func detectDistro() string {
	content, err := os.ReadFile("/etc/os-release")
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(content), "\n") {
		if strings.HasPrefix(line, "PRETTY_NAME=") {
			val := strings.TrimPrefix(line, "PRETTY_NAME=")
			val = strings.Trim(val, `"`)
			return val
		}
	}
	return ""
}

func pass(msg string) CheckResult { return CheckResult{Level: "PASS", Message: msg} }
func fail(msg string) CheckResult { return CheckResult{Level: "FAIL", Message: msg} }
func warn(msg string) CheckResult { return CheckResult{Level: "WARN", Message: msg} }
func info(msg string) CheckResult { return CheckResult{Level: "INFO", Message: msg} }

func printResult(out *output.Output, r CheckResult) {
	out.Info(fmt.Sprintf("  [%s] %s", r.Level, r.Message))
}
