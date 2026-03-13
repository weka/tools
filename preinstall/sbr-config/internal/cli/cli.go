// Package cli implements argument parsing and mode dispatch for sbr-config.
package cli

import (
	"fmt"
	"log"
	"os"

	flag "github.com/spf13/pflag"

	"github.com/weka/tools/preinstall/sbr-config/internal/configurator"
	"github.com/weka/tools/preinstall/sbr-config/internal/detector"
	"github.com/weka/tools/preinstall/sbr-config/internal/errors"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/logging"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/output"
	"github.com/weka/tools/preinstall/sbr-config/internal/persistence"
	"github.com/weka/tools/preinstall/sbr-config/internal/planner"
	"github.com/weka/tools/preinstall/sbr-config/internal/prereqs"
	"github.com/weka/tools/preinstall/sbr-config/internal/rollback"
	"github.com/weka/tools/preinstall/sbr-config/internal/validator"
)

// Run is the main entry point. Returns the exit code.
func Run(version string, args []string) int {
	// Define flags.
	fs := flag.NewFlagSet("sbr-config", flag.ContinueOnError)
	fs.Usage = func() {
		fmt.Fprintf(os.Stderr, `sbr-config %s - Configure source-based routing for multi-NIC Linux systems.

Usage: sbr-config [MODE] [OPTIONS]

Modes (mutually exclusive, one required):
  -V, --validate          Check current SBR configuration and report findings
  -c, --configure         Compute and apply needed SBR changes
  -r, --rollback          Restore previous configuration from backup
  -p, --check-prereqs     Check that all required prerequisites are installed

Options:
  -f, --force              Skip interactive confirmation (use with -c/--configure)
  -P, --no-persist         Skip writing persistent config (persist is on by default)
  -n, --dry-run            Show proposed changes without applying them
  -t, --confirm-timeout N  Seconds for post-apply confirmation (default: 30, 0=disable)
  -x, --exclude IFACE      Exclude interface from SBR (repeatable)
  -i, --include IFACE      Only configure these interfaces (repeatable)
  -b, --backup-file PATH   Specific backup file to restore from (with -r/--rollback)
  -l, --log-file PATH      Log file path (default: /var/log/sbr-config.log)
  -C, --no-color           Disable colored output
  -v, --verbose            Increase verbosity (use -vv for debug)
  -q, --quiet              Suppress non-error output
      --version            Show version and exit

Examples:
  sbr-config -V                      Check current SBR state
  sbr-config -c                      Apply changes + persist (default)
  sbr-config -c -f                   Apply without pre-apply confirmation
  sbr-config -c --no-persist         Apply runtime only, skip persistence
  sbr-config -c -n                   Show changes without applying
  sbr-config -r                      Restore previous state
  sbr-config -p                      Verify all prerequisites are met
  sbr-config -c -t 60               Wait 60s for post-apply check
  sbr-config -c -t 0                Disable post-apply safety timer
  sbr-config -c -x eth0             Exclude eth0 from SBR
  sbr-config -c -i eth1 -i eth2     Only configure eth1 and eth2

Safety:
  After applying changes, the tool waits for you to confirm that you still
  have connectivity (default: 30 seconds).  If you lose access and cannot
  respond, all changes are automatically rolled back.
`, version)
	}

	// Mode flags.
	validate := fs.BoolP("validate", "V", false, "")
	configure := fs.BoolP("configure", "c", false, "")
	doRollback := fs.BoolP("rollback", "r", false, "")
	checkPrereqs := fs.BoolP("check-prereqs", "p", false, "")

	// Option flags.
	force := fs.BoolP("force", "f", false, "")
	noPersist := fs.BoolP("no-persist", "P", false, "")
	dryRun := fs.BoolP("dry-run", "n", false, "")
	confirmTimeout := fs.IntP("confirm-timeout", "t", 30, "")
	exclude := fs.StringArrayP("exclude", "x", nil, "")
	include := fs.StringArrayP("include", "i", nil, "")
	backupFile := fs.StringP("backup-file", "b", "", "")
	logFile := fs.StringP("log-file", "l", "/var/log/sbr-config.log", "")
	noColor := fs.BoolP("no-color", "C", false, "")
	verbose := fs.CountP("verbose", "v", "")
	quiet := fs.BoolP("quiet", "q", false, "")
	showVersion := fs.Bool("version", false, "")

	if err := fs.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		fmt.Fprintf(os.Stderr, "Run 'sbr-config --help' for usage.\n")
		return 1
	}

	// Handle --version.
	if *showVersion {
		fmt.Printf("sbr-config %s\n", version)
		return 0
	}

	// Mutual exclusion check.
	modeCount := 0
	if *validate {
		modeCount++
	}
	if *configure {
		modeCount++
	}
	if *doRollback {
		modeCount++
	}
	if *checkPrereqs {
		modeCount++
	}
	if modeCount == 0 {
		fmt.Fprintln(os.Stderr, "Error: one of --validate, --configure, --rollback, or --check-prereqs is required.")
		fmt.Fprintln(os.Stderr, "Run 'sbr-config --help' for usage.")
		return 1
	}
	if modeCount > 1 {
		fmt.Fprintln(os.Stderr, "Error: --validate, --configure, --rollback, and --check-prereqs are mutually exclusive.")
		return 1
	}

	// Setup logging and output.
	logging.Setup(logFile, *verbose)
	out := output.New(!*noColor, *quiet)

	// --check-prereqs can run without root / on any OS.
	if *checkPrereqs {
		return prereqs.CheckPrereqs(out)
	}

	// All other modes require root.
	if err := exec.CheckRoot(); err != nil {
		out.Error(err.Error())
		return 1
	}

	// Dispatch.
	var exitCode int
	defer func() {
		if r := recover(); r != nil {
			out.Error(fmt.Sprintf("Unexpected panic: %v", r))
			exitCode = 1
		}
	}()

	switch {
	case *validate:
		exitCode = doValidate(out, *exclude, *include)
	case *configure:
		exitCode = doConfigure(out, *exclude, *include, *force, *noPersist,
			*dryRun, *confirmTimeout)
	case *doRollback:
		exitCode = doRollbackMode(out, *force, *backupFile)
	}

	return exitCode
}

// ---------------------------------------------------------------------------
// Mode implementations
// ---------------------------------------------------------------------------

func doValidate(out *output.Output, exclude, include []string) int {
	out.Banner()
	out.Header("Detecting System State")

	state, err := detector.DetectSystemState(exclude, include)
	if err != nil {
		out.Error(fmt.Sprintf("Detection failed: %v", err))
		return 1
	}

	out.Info(fmt.Sprintf("Network manager: %s", state.NetworkManager))
	out.InterfaceTable(state.Interfaces)

	out.Header("Validation Results")
	results := validator.Validate(state)
	out.ValidationReport(results)

	passed := 0
	failed := 0
	for _, r := range results {
		if r.IsCorrect {
			passed++
		} else {
			failed++
		}
	}
	out.Summary(passed, failed)

	if failed > 0 {
		out.NL()
		out.Info("Run 'sbr-config --configure' to fix detected issues.")
		return 1
	}

	return 0
}

func doConfigure(
	out *output.Output,
	exclude, include []string,
	force, noPersist, dryRun bool,
	confirmTimeout int,
) int {
	// Acquire lock.
	lock := exec.NewFileLock()
	if err := lock.Acquire(); err != nil {
		out.Error(fmt.Sprintf("Cannot acquire lock: %v", err))
		return 1
	}
	defer lock.Release()

	out.Banner()
	out.Header("Detecting System State")

	state, err := detector.DetectSystemState(exclude, include)
	if err != nil {
		out.Error(fmt.Sprintf("Detection failed: %v", err))
		return 1
	}

	out.Info(fmt.Sprintf("Network manager: %s", state.NetworkManager))
	out.InterfaceTable(state.Interfaces)

	// Validate.
	out.Header("Validating Current Configuration")
	results := validator.Validate(state)

	passed := 0
	failed := 0
	for _, r := range results {
		if r.IsCorrect {
			passed++
		} else {
			failed++
		}
	}
	out.Summary(passed, failed)

	if failed == 0 {
		out.NL()
		out.Info("System is correctly configured for source-based routing.")
		// Even though runtime is correct, persistence files may be
		// missing or stale. Regenerate so config survives reboot.
		if !noPersist {
			writePersistence(state, nil, out)
		}
		return 0
	}

	// Plan changes.
	out.Header("Proposed Changes")
	changes := planner.PlanChanges(state, results)

	if len(changes) == 0 {
		out.Info("No actionable changes could be planned.")
		out.Info("Some issues may require manual intervention.")
		return 1
	}

	out.ChangesReport(changes)

	// Dry run stops here.
	if dryRun {
		out.NL()
		out.Info("Dry run complete. No changes were made.")
		return 0
	}

	// Interactive confirmation.
	if !force {
		if !out.PromptYN(
			fmt.Sprintf("Apply %d change(s) to the system?", len(changes)),
			false,
		) {
			out.Info("Aborted by user. No changes made.")
			return 0
		}
	}

	// Save state for rollback.
	out.Header("Applying Changes")
	backupPath, err := rollback.SaveState(state)
	if err != nil {
		out.Error(fmt.Sprintf("Failed to save backup: %v", err))
		return 1
	}
	out.Info(fmt.Sprintf("State backup saved to: %s", backupPath))

	// Apply changes.
	applied, err := configurator.ApplyChanges(changes)
	if err != nil {
		out.Error(err.Error())
		return 1
	}
	out.NL()
	out.Info(fmt.Sprintf("Successfully applied %d change(s).", applied))

	// Dead man's switch.
	if confirmTimeout > 0 {
		confirmed := false
		func() {
			defer func() {
				if r := recover(); r != nil {
					confirmed = false
				}
			}()
			confirmed = out.PromptTimedConfirm(confirmTimeout)
		}()

		if !confirmed {
			out.NL()
			out.Error("No confirmation received -- rolling back all changes for safety.")
			if err := rollback.Rollback(backupPath); err != nil {
				out.Error(fmt.Sprintf("Auto-rollback failed: %v", err))
				out.Error(fmt.Sprintf("Manual rollback: sbr-config --rollback --backup-file %s", backupPath))
			} else {
				out.Info("Rollback complete. System restored to previous state.")
			}
			return 1
		}

		out.NL()
		out.Info("Confirmation received -- changes will be kept.")
	}

	// Write persistent config (default) unless --no-persist.
	if !noPersist {
		out.Header("Writing Persistent Configuration")
		writePersistence(state, changes, out)
	}

	out.NL()
	out.Info("Source-based routing is now configured.")
	out.Info("To undo these changes: sbr-config --rollback")

	return 0
}

func doRollbackMode(out *output.Output, force bool, backupFile string) int {
	// Acquire lock.
	lock := exec.NewFileLock()
	if err := lock.Acquire(); err != nil {
		out.Error(fmt.Sprintf("Cannot acquire lock: %v", err))
		return 1
	}
	defer lock.Release()

	out.Banner()

	if !force {
		// Show available backups.
		backups := rollback.ListBackups()
		if len(backups) == 0 {
			out.Error("No backups found. Nothing to roll back.")
			return 1
		}

		out.Header("Available Backups")
		for _, b := range backups {
			marker := ""
			if b.IsLatest {
				marker = " (latest)"
			}
			out.Info(fmt.Sprintf("%s -- %s%s", b.Timestamp, b.Path, marker))
		}

		if backupFile == "" {
			if !out.PromptYN("Restore from the latest backup?", false) {
				out.Info("Aborted.")
				return 0
			}
		}
	}

	out.Header("Rolling Back")
	if err := rollback.Rollback(backupFile); err != nil {
		out.Error(err.Error())
		return 1
	}
	out.NL()
	out.Info("Rollback complete. Previous SBR configuration has been removed.")
	out.Info("Run 'sbr-config --validate' to verify the current state.")

	return 0
}

// ---------------------------------------------------------------------------
// Persistence helper
// ---------------------------------------------------------------------------

func writePersistence(
	state *models.SystemState,
	changes []models.PlannedChange,
	out *output.Output,
) {
	files, err := persistence.WritePersistence(state, changes)
	if err != nil {
		// Check if it's a known sbr-config error.
		if _, ok := err.(*errors.PersistenceError); ok {
			out.Warning(fmt.Sprintf("Persistence failed: %v", err))
			out.Warning("Runtime changes are active but may not survive reboot.")
		} else {
			out.Warning(fmt.Sprintf("Persistence failed: %v", err))
			out.Warning("Runtime changes are active but may not survive reboot.")
		}
		return
	}
	for _, f := range files {
		out.Info(fmt.Sprintf("Wrote: %s", f))
	}

	log.Printf("[INFO] Wrote %d persistence file(s)", len(files))
}
