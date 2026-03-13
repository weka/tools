// Package output provides colored terminal output, formatted tables,
// and interactive prompts including the dead man's switch.
package output

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/weka/tools/preinstall/sbr-config/internal/models"
)

// ANSI color codes.
const (
	Reset   = "\033[0m"
	Bold    = "\033[1m"
	Dim     = "\033[2m"
	Red     = "\033[31m"
	Green   = "\033[32m"
	Yellow  = "\033[33m"
	Blue    = "\033[34m"
	Magenta = "\033[35m"
	Cyan    = "\033[36m"
	White   = "\033[37m"
)

// Output handles all user-facing terminal output.
type Output struct {
	color bool
	quiet bool
}

// New creates an Output instance.
func New(color, quiet bool) *Output {
	return &Output{color: color, quiet: quiet}
}

// c applies an ANSI color code if colors are enabled.
func (o *Output) c(code, text string) string {
	if !o.color {
		return text
	}
	return code + text + Reset
}

// Header prints a section header.
func (o *Output) Header(text string) {
	if o.quiet {
		return
	}
	fmt.Println()
	fmt.Println(o.c(Bold+Blue, text))
	fmt.Println(o.c(Bold+Blue, strings.Repeat("=", len(text))))
}

// Subheader prints a sub-section header.
func (o *Output) Subheader(text string) {
	if o.quiet {
		return
	}
	fmt.Println()
	fmt.Println(o.c(Bold+Cyan, text))
	fmt.Println(o.c(Dim, strings.Repeat("-", len(text))))
}

// Success prints a success message.
func (o *Output) Success(text string) {
	if o.quiet {
		return
	}
	fmt.Printf("  %s %s\n", o.c(Green, "[PASS]"), text)
}

// Fail prints a failure message.
func (o *Output) Fail(text string) {
	fmt.Printf("  %s %s\n", o.c(Red, "[FAIL]"), text)
}

// Warning prints a warning message.
func (o *Output) Warning(text string) {
	fmt.Printf("  %s %s\n", o.c(Yellow, "[WARN]"), text)
}

// Error prints an error message to stderr.
func (o *Output) Error(text string) {
	fmt.Fprintf(os.Stderr, "%s %s\n", o.c(Red+Bold, "ERROR:"), text)
}

// Info prints an informational message.
func (o *Output) Info(text string) {
	if o.quiet {
		return
	}
	fmt.Printf("  %s %s\n", o.c(Cyan, "[INFO]"), text)
}

// Dim prints dimmed/secondary text.
func (o *Output) Dim(text string) {
	if o.quiet {
		return
	}
	fmt.Printf("  %s\n", o.c(Dim, text))
}

// NL prints a blank line.
func (o *Output) NL() {
	if !o.quiet {
		fmt.Println()
	}
}

// Banner prints the tool banner.
func (o *Output) Banner() {
	if o.quiet {
		return
	}
	title := "sbr-config: Source-Based Routing Configurator"
	fmt.Println()
	fmt.Println(o.c(Bold+White, title))
	fmt.Println(o.c(Dim, strings.Repeat("=", len(title))))
}

// InterfaceTable prints a formatted table of detected interfaces.
func (o *Output) InterfaceTable(interfaces []models.InterfaceInfo) {
	if o.quiet {
		return
	}
	const fmtStr = "  %-12s %-20s %-16s %s\n"
	fmt.Printf(fmtStr, "INTERFACE", "IP/PREFIX", "GATEWAY", "STATUS")
	fmt.Printf(fmtStr,
		strings.Repeat("-", 11),
		strings.Repeat("-", 19),
		strings.Repeat("-", 15),
		strings.Repeat("-", 20),
	)
	for _, iface := range interfaces {
		if iface.IsLoopback {
			continue
		}
		gw := iface.GatewayStr()
		var statusParts []string
		if iface.IsDefaultRouteInterface {
			statusParts = append(statusParts, o.c(Green, "DEFAULT ROUTE"))
		}
		if !iface.IsUp {
			statusParts = append(statusParts, o.c(Yellow, "DOWN"))
		}
		status := strings.Join(statusParts, " | ")
		if status == "" {
			status = o.c(Dim, "secondary")
		}
		fmt.Printf(fmtStr, iface.Name, iface.CIDR(), gw, status)
	}
}

// ValidationReport prints a formatted validation report.
func (o *Output) ValidationReport(results []models.ValidationResult) {
	if len(results) == 0 {
		o.Info("No validation checks to report.")
		return
	}

	currentIface := ""
	for _, r := range results {
		if r.InterfaceName != currentIface {
			currentIface = r.InterfaceName
			o.Subheader(fmt.Sprintf("Interface: %s", currentIface))
		}

		if r.IsCorrect {
			o.Success(fmt.Sprintf("%s: %s", r.CheckName, r.CurrentValue))
		} else {
			o.Fail(r.CheckName)
			o.Dim(fmt.Sprintf("  Current:  %s", r.CurrentValue))
			o.Dim(fmt.Sprintf("  Expected: %s", r.ExpectedValue))
			if r.FixDescription != "" {
				o.Dim(fmt.Sprintf("  Fix:      %s", r.FixDescription))
			}
		}
	}
}

// ChangesReport prints proposed changes with explanations.
func (o *Output) ChangesReport(changes []models.PlannedChange) {
	if len(changes) == 0 {
		o.Info("No changes needed -- system is correctly configured.")
		return
	}

	for i, change := range changes {
		tag := o.c(Bold+Yellow, fmt.Sprintf("  %d.", i+1))
		desc := o.c(Bold, change.Description)
		fmt.Printf("%s %s\n", tag, desc)

		cmdPrefix := o.c(Dim, "     CMD:")
		cmd := o.c(Cyan, change.Command)
		fmt.Printf("%s %s\n", cmdPrefix, cmd)

		reasonPrefix := o.c(Dim, "     WHY:")
		lines := wrapText(change.Reason, 65)
		fmt.Printf("%s %s\n", reasonPrefix, lines[0])
		for _, line := range lines[1:] {
			fmt.Printf("          %s\n", line)
		}
		fmt.Println()
	}
}

// PromptYN prompts the user for a yes/no answer.
func (o *Output) PromptYN(question string, defaultYes bool) bool {
	suffix := "[y/N]"
	if defaultYes {
		suffix = "[Y/n]"
	}
	fmt.Printf("\n%s %s: ", question, suffix)

	scanner := bufio.NewScanner(os.Stdin)
	if !scanner.Scan() {
		fmt.Println()
		return false
	}
	answer := strings.TrimSpace(strings.ToLower(scanner.Text()))
	if answer == "" {
		return defaultYes
	}
	return answer == "y" || answer == "yes"
}

// PromptTimedConfirm implements the post-apply dead man's switch.
// It displays a prominent warning and waits for the user to type 'yes'
// within timeout seconds. Returns true if confirmed, false if timeout
// expired or input was anything other than 'yes'.
func (o *Output) PromptTimedConfirm(timeout int) bool {
	boxW := 66
	border := o.c(Red+Bold, strings.Repeat("#", boxW))
	pad := o.c(Red+Bold, "#") + strings.Repeat(" ", boxW-2) + o.c(Red+Bold, "#")

	fmt.Println()
	fmt.Println(border)
	fmt.Println(pad)
	o.boxLine("CONNECTIVITY CHECK", boxW, Red+Bold)
	fmt.Println(pad)
	o.boxLine("Changes have been applied. Please verify that you", boxW, Yellow)
	o.boxLine("still have connectivity to this system.", boxW, Yellow)
	fmt.Println(pad)
	o.boxLine(fmt.Sprintf("Type 'yes' within %d seconds to KEEP the changes.", timeout), boxW, White+Bold)
	o.boxLine("If no response is received, all changes will be", boxW, White)
	o.boxLine("AUTOMATICALLY ROLLED BACK for safety.", boxW, White)
	fmt.Println(pad)
	fmt.Println(border)
	fmt.Println()

	deadline := time.Now().Add(time.Duration(timeout) * time.Second)

	// Channel to receive stdin lines from a goroutine.
	lineCh := make(chan string, 1)
	go func() {
		scanner := bufio.NewScanner(os.Stdin)
		for scanner.Scan() {
			lineCh <- scanner.Text()
		}
		close(lineCh)
	}()

	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			break
		}

		secs := int(remaining.Seconds() + 0.5)
		fmt.Fprintf(os.Stdout, "\r%s Type 'yes' to confirm: ",
			o.c(Yellow+Bold, fmt.Sprintf("  [%2ds]", secs)))

		select {
		case line, ok := <-lineCh:
			if !ok {
				// stdin closed
				goto done
			}
			answer := strings.TrimSpace(strings.ToLower(line))
			if answer == "yes" {
				fmt.Fprintf(os.Stdout, "\r%s\r", strings.Repeat(" ", 60))
				return true
			}
			if answer != "" {
				fmt.Fprintf(os.Stdout, "  %s\n", o.c(Red, "Please type exactly 'yes' to confirm."))
			}
		case <-ticker.C:
			// Redraw countdown
		}
	}

done:
	fmt.Fprintf(os.Stdout, "\r%s\r", strings.Repeat(" ", 60))
	return false
}

// boxLine prints a centered line inside a bordered box.
func (o *Output) boxLine(text string, width int, colorCode string) {
	inner := width - 4 // account for "# " and " #"
	padded := centerStr(text, inner)
	left := o.c(Red+Bold, "# ")
	right := o.c(Red+Bold, " #")
	middle := o.c(colorCode, padded)
	fmt.Println(left + middle + right)
}

// Summary prints a validation summary line.
func (o *Output) Summary(passed, failed int) {
	total := passed + failed
	var msg string
	if failed == 0 {
		msg = o.c(Green+Bold, fmt.Sprintf("All %d checks passed", total))
	} else {
		msg = o.c(Green, fmt.Sprintf("%d passed", passed)) +
			", " +
			o.c(Red+Bold, fmt.Sprintf("%d failed", failed)) +
			fmt.Sprintf(" (out of %d)", total)
	}
	fmt.Println()
	fmt.Printf("  Summary: %s\n", msg)
}

// wrapText is a simple word-wrap without importing textwrap.
func wrapText(text string, width int) []string {
	words := strings.Fields(text)
	if len(words) == 0 {
		return []string{""}
	}
	var lines []string
	current := ""
	for _, word := range words {
		if current != "" && len(current)+1+len(word) > width {
			lines = append(lines, current)
			current = word
		} else if current != "" {
			current += " " + word
		} else {
			current = word
		}
	}
	if current != "" {
		lines = append(lines, current)
	}
	return lines
}

// centerStr center-pads a string within the given width.
func centerStr(s string, width int) string {
	if len(s) >= width {
		return s
	}
	left := (width - len(s)) / 2
	right := width - len(s) - left
	return strings.Repeat(" ", left) + s + strings.Repeat(" ", right)
}
