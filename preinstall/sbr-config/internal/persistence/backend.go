// Package persistence provides backend dispatch and persistence file writing.
package persistence

import (
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
)

// Backend is the interface that all persistence backends must implement.
type Backend interface {
	// WriteConfig writes persistent configuration files.
	// Returns the list of file paths that were created or modified.
	WriteConfig(interfaces []models.InterfaceInfo, tables []models.RoutingTable) ([]string, error)

	// RemoveConfig removes previously written persistent configuration.
	// Returns the list of file paths that were removed or restored.
	RemoveConfig() []string

	// Describe returns a human-readable description of what this backend
	// writes and where.
	Describe() string
}
