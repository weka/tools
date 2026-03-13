// Package models defines the core data structures used throughout sbr-config.
package models

import (
	"fmt"
	"strings"
)

// NetworkManagerType describes the detected network management subsystem.
type NetworkManagerType string

const (
	NMNetworkManager    NetworkManagerType = "NetworkManager"
	NMSystemdNetworkd   NetworkManagerType = "systemd-networkd"
	NMIfupdown          NetworkManagerType = "ifupdown"
	NMNetplanNetworkd   NetworkManagerType = "netplan+systemd-networkd"
	NMNetplanNM         NetworkManagerType = "netplan+NetworkManager"
	NMUnknown           NetworkManagerType = "unknown"
)

// ChangeType describes the kind of planned change.
type ChangeType string

const (
	ChangeAddRTTable ChangeType = "add_routing_table"
	ChangeAddRoute   ChangeType = "add_route"
	ChangeAddRule    ChangeType = "add_rule"
	ChangeSetSysctl  ChangeType = "set_sysctl"
	ChangeDelRoute   ChangeType = "delete_route"
	ChangeDelRule    ChangeType = "delete_rule"
)

// InterfaceInfo represents a discovered network interface.
type InterfaceInfo struct {
	Name                    string  `json:"name"`
	IPAddress               string  `json:"ip_address"`
	PrefixLength            int     `json:"prefix_length"`
	Subnet                  string  `json:"subnet"`
	Gateway                 *string `json:"gateway"`
	MACAddress              string  `json:"mac_address"`
	IsUp                    bool    `json:"is_up"`
	IsLoopback              bool    `json:"is_loopback"`
	IsDefaultRouteInterface bool    `json:"is_default_route_interface"`
	MTU                     int     `json:"mtu"`
}

// CIDR returns "ip/prefix".
func (i *InterfaceInfo) CIDR() string {
	return fmt.Sprintf("%s/%d", i.IPAddress, i.PrefixLength)
}

// GatewayStr returns the gateway or "(none)" for display.
func (i *InterfaceInfo) GatewayStr() string {
	if i.Gateway != nil {
		return *i.Gateway
	}
	return "(none)"
}

// RoutingTable represents an entry in /etc/iproute2/rt_tables.
type RoutingTable struct {
	Number int    `json:"number"`
	Name   string `json:"name"`
}

// Route represents a single ip route entry.
type Route struct {
	Destination string  `json:"destination"`
	Gateway     *string `json:"gateway"`
	Device      string  `json:"device"`
	Source      *string `json:"source"`
	Table       *string `json:"table"`
	Metric      *int    `json:"metric"`
	Scope       *string `json:"scope"`
	Protocol    *string `json:"protocol"`
}

// ToArgs converts the route to ip-route command arguments.
func (r *Route) ToArgs() string {
	parts := []string{r.Destination}
	if r.Gateway != nil {
		parts = append(parts, "via", *r.Gateway)
	}
	parts = append(parts, "dev", r.Device)
	if r.Source != nil {
		parts = append(parts, "src", *r.Source)
	}
	if r.Table != nil {
		parts = append(parts, "table", *r.Table)
	}
	if r.Metric != nil {
		parts = append(parts, "metric", fmt.Sprintf("%d", *r.Metric))
	}
	if r.Scope != nil {
		parts = append(parts, "scope", *r.Scope)
	}
	return strings.Join(parts, " ")
}

// Rule represents a single ip rule entry.
type Rule struct {
	Priority     int     `json:"priority"`
	SelectorFrom *string `json:"selector_from"`
	SelectorTo   *string `json:"selector_to"`
	Table        *string `json:"table"`
	IIF          *string `json:"iif"`
	FWMark       *string `json:"fwmark"`
}

// ToArgs converts the rule to ip-rule command arguments.
func (r *Rule) ToArgs() string {
	var parts []string
	if r.SelectorFrom != nil {
		parts = append(parts, "from", *r.SelectorFrom)
	}
	if r.SelectorTo != nil {
		parts = append(parts, "to", *r.SelectorTo)
	}
	if r.Table != nil {
		parts = append(parts, "table", *r.Table)
	}
	if r.IIF != nil {
		parts = append(parts, "iif", *r.IIF)
	}
	if r.FWMark != nil {
		parts = append(parts, "fwmark", *r.FWMark)
	}
	parts = append(parts, "priority", fmt.Sprintf("%d", r.Priority))
	return strings.Join(parts, " ")
}

// SysctlSetting represents a sysctl key/value pair with its required state.
type SysctlSetting struct {
	Key           string `json:"key"`
	CurrentValue  *string `json:"current_value"`
	RequiredValue string `json:"required_value"`
	Description   string `json:"description"`
	Reason        string `json:"reason"`
}

// IsCorrect returns whether the current value matches the required value.
func (s *SysctlSetting) IsCorrect() bool {
	return s.CurrentValue != nil && *s.CurrentValue == s.RequiredValue
}

// SystemState is a complete snapshot of current routing state for backup/comparison.
type SystemState struct {
	Interfaces          []InterfaceInfo        `json:"interfaces"`
	RoutingTables       []RoutingTable         `json:"routing_tables"`
	RoutesMain          []Route                `json:"routes_main"`
	RoutesByTable       map[string][]Route     `json:"routes_by_table"`
	Rules               []Rule                 `json:"rules"`
	RTTablesFileContent string                 `json:"rt_tables_file_content"`
	SysctlValues        map[string]string      `json:"sysctl_values"`
	NetworkManager      NetworkManagerType     `json:"network_manager"`
	Timestamp           string                 `json:"timestamp"`
}

// PlannedChange represents a single atomic change to be applied.
type PlannedChange struct {
	ChangeType      ChangeType `json:"change_type"`
	Description     string     `json:"description"`
	Reason          string     `json:"reason"`
	Command         string     `json:"command"`
	Interface       *string    `json:"interface"`
	RollbackCommand *string    `json:"rollback_command"`
}

// ValidationResult holds the result of validating one aspect of SBR config.
type ValidationResult struct {
	InterfaceName  string `json:"interface_name"`
	CheckName      string `json:"check_name"`
	IsCorrect      bool   `json:"is_correct"`
	CurrentValue   string `json:"current_value"`
	ExpectedValue  string `json:"expected_value"`
	FixDescription string `json:"fix_description"`
}

// StatusSymbol returns "PASS" or "FAIL".
func (v *ValidationResult) StatusSymbol() string {
	if v.IsCorrect {
		return "PASS"
	}
	return "FAIL"
}

// StrPtr is a helper to create a *string from a string literal.
func StrPtr(s string) *string {
	return &s
}

// IntPtr is a helper to create an *int from an int literal.
func IntPtr(i int) *int {
	return &i
}
