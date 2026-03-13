// Package exec provides shell command execution, atomic file writes,
// privilege checks, and file-based locking.
package exec

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/errors"
)

// CommandResult holds the output of a shell command.
type CommandResult struct {
	Stdout     string
	Stderr     string
	ExitCode   int
}

// RunCommand executes a shell command string and returns its output.
// If check is true, a non-zero exit code returns a ConfigurationError.
func RunCommand(cmd string, check bool, timeoutSec int) (*CommandResult, error) {
	if timeoutSec <= 0 {
		timeoutSec = 10
	}

	log.Printf("[DEBUG] Running: %s", cmd)

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSec)*time.Second)
	defer cancel()

	c := exec.CommandContext(ctx, "/bin/sh", "-c", cmd)
	var stdout, stderr strings.Builder
	c.Stdout = &stdout
	c.Stderr = &stderr

	err := c.Run()

	result := &CommandResult{
		Stdout: stdout.String(),
		Stderr: stderr.String(),
	}

	if ctx.Err() == context.DeadlineExceeded {
		return result, errors.NewConfigurationError("Command timed out after %ds: %s", timeoutSec, cmd)
	}

	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			result.ExitCode = exitErr.ExitCode()
		} else {
			return result, errors.NewConfigurationError("Command failed to start: %s: %v", cmd, err)
		}
	}

	if result.Stdout != "" {
		log.Printf("[DEBUG] stdout: %s", strings.TrimRight(result.Stdout, "\n"))
	}
	if result.Stderr != "" {
		log.Printf("[DEBUG] stderr: %s", strings.TrimRight(result.Stderr, "\n"))
	}

	if check && result.ExitCode != 0 {
		return result, errors.NewConfigurationError(
			"Command failed (exit %d): %s\nstderr: %s",
			result.ExitCode, cmd, strings.TrimRight(result.Stderr, "\n"),
		)
	}
	return result, nil
}

// WriteFileAtomic writes content to path via a temp file + rename.
// If mode is 0, it preserves the existing file mode or defaults to 0644.
func WriteFileAtomic(path, content string, mode os.FileMode) error {
	tmpPath := path + ".sbr-config.tmp"

	if mode == 0 {
		if info, err := os.Stat(path); err == nil {
			mode = info.Mode().Perm()
		} else {
			mode = 0644
		}
	}

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("create directory %s: %w", dir, err)
	}

	if err := os.WriteFile(tmpPath, []byte(content), mode); err != nil {
		return fmt.Errorf("write temp file %s: %w", tmpPath, err)
	}

	if err := os.Chmod(tmpPath, mode); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("chmod %s: %w", tmpPath, err)
	}

	if err := os.Rename(tmpPath, path); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("rename %s → %s: %w", tmpPath, path, err)
	}

	log.Printf("[DEBUG] Wrote %s (%d bytes)", path, len(content))
	return nil
}

// ReadFile reads a file's contents, returning "" and nil if it doesn't exist.
func ReadFile(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		if os.IsPermission(err) {
			log.Printf("[WARN] Permission denied reading %s", path)
			return "", nil
		}
		return "", err
	}
	return string(data), nil
}

// CheckRoot verifies the current user is root (euid 0).
func CheckRoot() error {
	if os.Geteuid() != 0 {
		return errors.NewPrivilegeError("sbr-config must be run as root (try: sudo sbr-config ...)")
	}
	return nil
}

// IsLinux returns true if the current platform is Linux.
func IsLinux() bool {
	return runtime.GOOS == "linux"
}

// CommandExists checks if a command is available in PATH.
func CommandExists(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

// IPJSONSupported checks whether `ip -j` (JSON output) works.
func IPJSONSupported() bool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	out, err := exec.CommandContext(ctx, "/bin/sh", "-c", "ip -j link show lo").Output()
	if err != nil {
		return false
	}
	return strings.HasPrefix(strings.TrimSpace(string(out)), "[")
}

// FileLock provides a simple file-based lock using flock(2).
type FileLock struct {
	path string
	fd   *os.File
}

// NewFileLock creates a new FileLock with the default lock path.
func NewFileLock() *FileLock {
	return &FileLock{path: constants.LockFile}
}

// Acquire attempts to take the lock. Returns a LockError if already held.
func (fl *FileLock) Acquire() error {
	dir := filepath.Dir(fl.path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("create lock dir %s: %w", dir, err)
	}

	fd, err := os.OpenFile(fl.path, os.O_WRONLY|os.O_CREATE, 0644)
	if err != nil {
		return fmt.Errorf("open lock file %s: %w", fl.path, err)
	}

	if err := syscall.Flock(int(fd.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		fd.Close()
		return errors.NewLockError(
			"Another sbr-config instance is running. If this is wrong, remove %s",
			fl.path,
		)
	}

	fmt.Fprintf(fd, "%d", os.Getpid())
	fd.Sync()
	fl.fd = fd
	return nil
}

// Release releases the lock and removes the lock file.
func (fl *FileLock) Release() {
	if fl.fd == nil {
		return
	}
	syscall.Flock(int(fl.fd.Fd()), syscall.LOCK_UN)
	fl.fd.Close()
	os.Remove(fl.path)
	fl.fd = nil
}
