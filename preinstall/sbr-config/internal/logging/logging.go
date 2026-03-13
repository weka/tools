// Package logging configures file and console log output for sbr-config.
package logging

import (
	"io"
	"log"
	"os"
	"path/filepath"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
)

// Setup configures the Go standard logger.
//
// logFile controls the file handler:
//   - nil  → no file logging
//   - ""   → use default path (constants.LogFileDefault)
//   - path → use that path
//
// verbosity controls console output:
//
//	0 = only file logging (no console debug)
//	1 = INFO on console
//	2+ = DEBUG on console
func Setup(logFile *string, verbosity int) {
	var writers []io.Writer

	// File handler (always captures everything).
	if logFile != nil {
		path := *logFile
		if path == "" {
			path = constants.LogFileDefault
		}
		dir := filepath.Dir(path)
		if dir != "" {
			os.MkdirAll(dir, 0755)
		}
		f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err == nil {
			writers = append(writers, f)
		}
		// Non-fatal: if we can't open the log file, just skip it.
	}

	// Console handler (only when verbose).
	if verbosity >= 1 {
		writers = append(writers, os.Stderr)
	}

	if len(writers) == 0 {
		log.SetOutput(io.Discard)
	} else if len(writers) == 1 {
		log.SetOutput(writers[0])
	} else {
		log.SetOutput(io.MultiWriter(writers...))
	}

	log.SetFlags(log.Ldate | log.Ltime)
}
