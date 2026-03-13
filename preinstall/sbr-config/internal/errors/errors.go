// Package errors defines the error types used throughout sbr-config.
package errors

import "fmt"

// SbrConfigError is the base error type for sbr-config.
type SbrConfigError struct {
	Message string
}

func (e *SbrConfigError) Error() string { return e.Message }

// DetectionError indicates failure to detect interfaces, gateways, or system state.
type DetectionError struct{ SbrConfigError }

// ValidationError indicates validation found issues that prevent configuration.
type ValidationError struct{ SbrConfigError }

// ConfigurationError indicates failure to apply a configuration change.
type ConfigurationError struct{ SbrConfigError }

// PersistenceError indicates failure to write persistent configuration.
type PersistenceError struct{ SbrConfigError }

// RollbackError indicates failure to restore previous state.
type RollbackError struct{ SbrConfigError }

// PrivilegeError indicates insufficient privileges (not root).
type PrivilegeError struct{ SbrConfigError }

// LockError indicates the lock file could not be acquired (another instance running).
type LockError struct{ SbrConfigError }

// Helper constructors.

func NewDetectionError(msg string, args ...interface{}) *DetectionError {
	return &DetectionError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}

func NewValidationError(msg string, args ...interface{}) *ValidationError {
	return &ValidationError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}

func NewConfigurationError(msg string, args ...interface{}) *ConfigurationError {
	return &ConfigurationError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}

func NewPersistenceError(msg string, args ...interface{}) *PersistenceError {
	return &PersistenceError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}

func NewRollbackError(msg string, args ...interface{}) *RollbackError {
	return &RollbackError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}

func NewPrivilegeError(msg string, args ...interface{}) *PrivilegeError {
	return &PrivilegeError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}

func NewLockError(msg string, args ...interface{}) *LockError {
	return &LockError{SbrConfigError{fmt.Sprintf(msg, args...)}}
}
