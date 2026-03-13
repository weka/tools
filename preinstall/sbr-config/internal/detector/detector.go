// Package detector discovers interfaces, IPs, gateways, routes, rules,
// and the active network manager type.
package detector

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/weka/tools/preinstall/sbr-config/internal/constants"
	"github.com/weka/tools/preinstall/sbr-config/internal/errors"
	"github.com/weka/tools/preinstall/sbr-config/internal/exec"
	"github.com/weka/tools/preinstall/sbr-config/internal/models"
	"github.com/weka/tools/preinstall/sbr-config/internal/sysctl"
)

// -----------------------------------------------------------------------
// Regex patterns (compiled once).
// -----------------------------------------------------------------------

var (
	reIfaceHeader  = regexp.MustCompile(`^\d+:\s+(\S+?):\s+<([^>]*)>.*mtu\s+(\d+)`)
	reIfaceState   = regexp.MustCompile(`state\s+(\S+)`)
	reMACAddr      = regexp.MustCompile(`^\s+link/ether\s+([\da-f:]+)`)
	reIPv4Addr     = regexp.MustCompile(`^\s+inet\s+([\d.]+)/(\d+)`)
	reDefaultRoute = regexp.MustCompile(`^default\s+via\s+(\S+)\s+dev\s+(\S+)`)
	reRuleLine     = regexp.MustCompile(`^(\d+):\s*(.*)`)
	reViaGw        = regexp.MustCompile(`via\s+(\S+)`)
	reDHCPRouters  = regexp.MustCompile(`option\s+routers\s+([\d.]+)`)
	reDHCPRouter2  = regexp.MustCompile(`ROUTER=([\d.]+)`)
	reGatewayKey   = regexp.MustCompile(`Gateway\s*=\s*([\d.]+)`)
	reNetplanRend  = regexp.MustCompile(`renderer:\s*(\S+)`)
)

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

// DetectSystemState detects the complete system routing state.
func DetectSystemState(exclude, include []string) (*models.SystemState, error) {
	useJSON := exec.IPJSONSupported()
	if useJSON {
		log.Println("[INFO] ip JSON mode: supported")
	} else {
		log.Println("[INFO] ip JSON mode: fallback to text")
	}

	// Detect interfaces.
	interfaces, err := detectInterfaces(useJSON)
	if err != nil {
		return nil, err
	}

	// Filter interfaces.
	if len(include) > 0 {
		incSet := toSet(include)
		var filtered []models.InterfaceInfo
		for _, i := range interfaces {
			if i.IsLoopback || incSet[i.Name] {
				filtered = append(filtered, i)
			}
		}
		interfaces = filtered
	}
	if len(exclude) > 0 {
		excSet := toSet(exclude)
		var filtered []models.InterfaceInfo
		for _, i := range interfaces {
			if !excSet[i.Name] {
				filtered = append(filtered, i)
			}
		}
		interfaces = filtered
	}

	// Detect default route and mark the default interface.
	defaultGW, defaultDev := detectDefaultRoute(useJSON)
	for idx := range interfaces {
		isDefault := defaultDev != nil && interfaces[idx].Name == *defaultDev
		interfaces[idx].IsDefaultRouteInterface = isDefault
		if isDefault && interfaces[idx].Gateway == nil {
			interfaces[idx].Gateway = defaultGW
		}
	}

	// Detect gateways for non-default interfaces.
	for idx := range interfaces {
		iface := &interfaces[idx]
		if iface.IsLoopback || iface.IsDefaultRouteInterface {
			continue
		}
		if iface.Gateway == nil {
			iface.Gateway = detectGateway(iface, useJSON)
		}
	}

	// Detect routing tables.
	rtContent, _ := exec.ReadFile(constants.RTTablesPath)
	routingTables := parseRTTables(rtContent)

	// Detect routes and rules.
	routesMain := detectRoutes(useJSON, "main")
	routesByTable := make(map[string][]models.Route)
	for _, rt := range routingTables {
		tableRoutes := detectRoutes(useJSON, rt.Name)
		if len(tableRoutes) > 0 {
			routesByTable[rt.Name] = tableRoutes
		}
	}
	rules := detectRules(useJSON)

	// Detect sysctl values.
	var ifaceNames []string
	for _, i := range interfaces {
		if !i.IsLoopback {
			ifaceNames = append(ifaceNames, i.Name)
		}
	}
	sysctlValues := sysctl.ReadAllSysctlValues(ifaceNames)

	// Detect network manager.
	networkManager := detectNetworkManager()

	return &models.SystemState{
		Interfaces:          interfaces,
		RoutingTables:       routingTables,
		RoutesMain:          routesMain,
		RoutesByTable:       routesByTable,
		Rules:               rules,
		RTTablesFileContent: rtContent,
		SysctlValues:        sysctlValues,
		NetworkManager:      networkManager,
		Timestamp:           time.Now().UTC().Format(time.RFC3339),
	}, nil
}

// -----------------------------------------------------------------------
// Interface detection
// -----------------------------------------------------------------------

func detectInterfaces(useJSON bool) ([]models.InterfaceInfo, error) {
	if useJSON {
		return detectInterfacesJSON()
	}
	return detectInterfacesText()
}

// JSON structs for ip -j addr show.
type ipAddrEntry struct {
	IfName    string       `json:"ifname"`
	Flags     []string     `json:"flags"`
	OperState string       `json:"operstate"`
	Address   string       `json:"address"`
	MTU       int          `json:"mtu"`
	AddrInfo  []ipAddrInfo `json:"addr_info"`
}

type ipAddrInfo struct {
	Family    string `json:"family"`
	Local     string `json:"local"`
	PrefixLen int    `json:"prefixlen"`
}

func detectInterfacesJSON() ([]models.InterfaceInfo, error) {
	res, err := exec.RunCommand("ip -j addr show", true, 10)
	if err != nil {
		return nil, err
	}

	var entries []ipAddrEntry
	if err := json.Unmarshal([]byte(res.Stdout), &entries); err != nil {
		return nil, errors.NewDetectionError("Failed to parse 'ip -j addr show' output: %v", err)
	}

	var interfaces []models.InterfaceInfo
	for _, e := range entries {
		isLoopback := containsStr(e.Flags, "LOOPBACK")
		isUp := strings.EqualFold(e.OperState, "UP") || strings.EqualFold(e.OperState, "UNKNOWN")
		mtu := e.MTU
		if mtu == 0 {
			mtu = 1500
		}

		for _, ai := range e.AddrInfo {
			if ai.Family != "inet" || ai.Local == "" {
				continue
			}
			subnet := computeSubnet(ai.Local, ai.PrefixLen)

			interfaces = append(interfaces, models.InterfaceInfo{
				Name:                    e.IfName,
				IPAddress:               ai.Local,
				PrefixLength:            ai.PrefixLen,
				Subnet:                  subnet,
				Gateway:                 nil,
				MACAddress:              e.Address,
				IsUp:                    isUp,
				IsLoopback:              isLoopback,
				IsDefaultRouteInterface: false,
				MTU:                     mtu,
			})
		}
	}

	log.Printf("[INFO] Detected %d interfaces (JSON mode)", len(interfaces))
	return interfaces, nil
}

func detectInterfacesText() ([]models.InterfaceInfo, error) {
	res, err := exec.RunCommand("ip addr show", true, 10)
	if err != nil {
		return nil, err
	}

	var interfaces []models.InterfaceInfo
	var curName, curMAC, curFlags, curState string
	curMTU := 1500

	for _, line := range strings.Split(res.Stdout, "\n") {
		// Interface header.
		if m := reIfaceHeader.FindStringSubmatch(line); m != nil {
			curName = strings.TrimSuffix(m[1], ":")
			curFlags = m[2]
			curMTU, _ = strconv.Atoi(m[3])
			if sm := reIfaceState.FindStringSubmatch(line); sm != nil {
				curState = sm[1]
			} else {
				curState = "UNKNOWN"
			}
			continue
		}
		// MAC address.
		if m := reMACAddr.FindStringSubmatch(line); m != nil {
			curMAC = m[1]
			continue
		}
		// IPv4 address.
		if m := reIPv4Addr.FindStringSubmatch(line); m != nil {
			ipAddr := m[1]
			prefix, _ := strconv.Atoi(m[2])
			isLoopback := strings.Contains(curFlags, "LOOPBACK")
			isUp := strings.EqualFold(curState, "UP") || strings.EqualFold(curState, "UNKNOWN")
			subnet := computeSubnet(ipAddr, prefix)

			interfaces = append(interfaces, models.InterfaceInfo{
				Name:                    curName,
				IPAddress:               ipAddr,
				PrefixLength:            prefix,
				Subnet:                  subnet,
				Gateway:                 nil,
				MACAddress:              curMAC,
				IsUp:                    isUp,
				IsLoopback:              isLoopback,
				IsDefaultRouteInterface: false,
				MTU:                     curMTU,
			})
		}
	}

	log.Printf("[INFO] Detected %d interfaces (text mode)", len(interfaces))
	return interfaces, nil
}

// -----------------------------------------------------------------------
// Route detection
// -----------------------------------------------------------------------

func detectDefaultRoute(useJSON bool) (*string, *string) {
	if useJSON {
		res, err := exec.RunCommand("ip -j route show default", false, 10)
		if err == nil && strings.TrimSpace(res.Stdout) != "" {
			var routes []map[string]interface{}
			if json.Unmarshal([]byte(res.Stdout), &routes) == nil {
				for _, r := range routes {
					if dst, _ := r["dst"].(string); dst == "default" {
						gw, _ := r["gateway"].(string)
						dev, _ := r["dev"].(string)
						var gwPtr, devPtr *string
						if gw != "" {
							gwPtr = &gw
						}
						if dev != "" {
							devPtr = &dev
						}
						return gwPtr, devPtr
					}
				}
			}
		}
	}

	// Fallback: text parsing.
	res, _ := exec.RunCommand("ip route show default", false, 10)
	for _, line := range strings.Split(res.Stdout, "\n") {
		if m := reDefaultRoute.FindStringSubmatch(line); m != nil {
			gw := m[1]
			dev := m[2]
			return &gw, &dev
		}
	}

	log.Println("[WARN] No default route found")
	return nil, nil
}

func detectRoutes(useJSON bool, table string) []models.Route {
	if useJSON {
		res, err := exec.RunCommand(fmt.Sprintf("ip -j route show table %s", table), false, 10)
		if err == nil && strings.TrimSpace(res.Stdout) != "" {
			var data []map[string]interface{}
			if json.Unmarshal([]byte(res.Stdout), &data) == nil {
				var routes []models.Route
				for _, d := range data {
					routes = append(routes, parseRouteJSON(d, table))
				}
				return routes
			}
		}
	}

	// Fallback: text.
	res, _ := exec.RunCommand(fmt.Sprintf("ip route show table %s", table), false, 10)
	var routes []models.Route
	for _, line := range strings.Split(res.Stdout, "\n") {
		if r := parseRouteText(line, table); r != nil {
			routes = append(routes, *r)
		}
	}
	return routes
}

func parseRouteJSON(data map[string]interface{}, table string) models.Route {
	r := models.Route{
		Destination: jsonStr(data, "dst"),
		Device:      jsonStr(data, "dev"),
		Table:       models.StrPtr(table),
	}
	if v := jsonStr(data, "gateway"); v != "" {
		r.Gateway = &v
	}
	if v := jsonStr(data, "prefsrc"); v != "" {
		r.Source = &v
	}
	if v, ok := data["metric"].(float64); ok {
		i := int(v)
		r.Metric = &i
	}
	if v := jsonStr(data, "scope"); v != "" {
		r.Scope = &v
	}
	if v := jsonStr(data, "protocol"); v != "" {
		r.Protocol = &v
	}
	return r
}

func parseRouteText(line, table string) *models.Route {
	line = strings.TrimSpace(line)
	if line == "" {
		return nil
	}
	parts := strings.Fields(line)
	if len(parts) == 0 {
		return nil
	}

	r := models.Route{
		Destination: parts[0],
		Table:       models.StrPtr(table),
	}

	for i := 1; i < len(parts)-1; i++ {
		switch parts[i] {
		case "via":
			v := parts[i+1]
			r.Gateway = &v
			i++
		case "dev":
			r.Device = parts[i+1]
			i++
		case "src":
			v := parts[i+1]
			r.Source = &v
			i++
		case "metric":
			if n, err := strconv.Atoi(parts[i+1]); err == nil {
				r.Metric = &n
			}
			i++
		case "scope":
			v := parts[i+1]
			r.Scope = &v
			i++
		case "proto":
			v := parts[i+1]
			r.Protocol = &v
			i++
		}
	}
	return &r
}

// -----------------------------------------------------------------------
// Rule detection
// -----------------------------------------------------------------------

func detectRules(useJSON bool) []models.Rule {
	if useJSON {
		res, err := exec.RunCommand("ip -j rule show", false, 10)
		if err == nil && strings.TrimSpace(res.Stdout) != "" {
			var data []map[string]interface{}
			if json.Unmarshal([]byte(res.Stdout), &data) == nil {
				var rules []models.Rule
				for _, d := range data {
					rules = append(rules, parseRuleJSON(d))
				}
				return rules
			}
		}
	}

	// Fallback: text.
	res, _ := exec.RunCommand("ip rule show", false, 10)
	var rules []models.Rule
	for _, line := range strings.Split(res.Stdout, "\n") {
		if r := parseRuleText(line); r != nil {
			rules = append(rules, *r)
		}
	}
	return rules
}

func parseRuleJSON(data map[string]interface{}) models.Rule {
	r := models.Rule{
		Priority: jsonInt(data, "priority"),
	}
	if v := jsonStr(data, "src"); v != "" {
		r.SelectorFrom = &v
	}
	if v := jsonStr(data, "dst"); v != "" {
		r.SelectorTo = &v
	}
	if v := jsonStr(data, "table"); v != "" {
		r.Table = &v
	}
	if v := jsonStr(data, "iif"); v != "" {
		r.IIF = &v
	}
	if v := jsonStr(data, "fwmark"); v != "" {
		r.FWMark = &v
	}
	return r
}

func parseRuleText(line string) *models.Rule {
	line = strings.TrimSpace(line)
	if line == "" {
		return nil
	}

	m := reRuleLine.FindStringSubmatch(line)
	if m == nil {
		return nil
	}
	priority, _ := strconv.Atoi(m[1])
	rest := m[2]

	r := models.Rule{Priority: priority}

	parts := strings.Fields(rest)
	for i := 0; i < len(parts)-1; i++ {
		switch parts[i] {
		case "from":
			v := parts[i+1]
			if v != "all" {
				r.SelectorFrom = &v
			}
			i++
		case "to":
			v := parts[i+1]
			if v != "all" {
				r.SelectorTo = &v
			}
			i++
		case "lookup", "table":
			v := parts[i+1]
			r.Table = &v
			i++
		case "iif":
			v := parts[i+1]
			r.IIF = &v
			i++
		case "fwmark":
			v := parts[i+1]
			r.FWMark = &v
			i++
		}
	}
	return &r
}

// -----------------------------------------------------------------------
// Routing table file parsing
// -----------------------------------------------------------------------

func parseRTTables(content string) []models.RoutingTable {
	var tables []models.RoutingTable
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, " ", 2)
		if len(parts) < 2 {
			// Try tab split.
			parts = strings.SplitN(line, "\t", 2)
		}
		if len(parts) < 2 {
			continue
		}
		num, err := strconv.Atoi(strings.TrimSpace(parts[0]))
		if err != nil {
			continue
		}
		name := strings.TrimSpace(parts[1])
		tables = append(tables, models.RoutingTable{Number: num, Name: name})
	}
	return tables
}

// ParseRTTables is the exported version for use by other packages.
func ParseRTTables(content string) []models.RoutingTable {
	return parseRTTables(content)
}

// -----------------------------------------------------------------------
// Gateway detection for non-default interfaces
// -----------------------------------------------------------------------

func detectGateway(iface *models.InterfaceInfo, useJSON bool) *string {
	if gw := gatewayFromExistingRoutes(iface); gw != nil {
		log.Printf("[INFO] Gateway for %s from existing routes: %s", iface.Name, *gw)
		return gw
	}
	if gw := gatewayFromDHCPLeases(iface); gw != nil {
		log.Printf("[INFO] Gateway for %s from DHCP lease: %s", iface.Name, *gw)
		return gw
	}
	if gw := gatewayFromNmcli(iface); gw != nil {
		log.Printf("[INFO] Gateway for %s from nmcli: %s", iface.Name, *gw)
		return gw
	}
	if gw := gatewayFromNetworkd(iface); gw != nil {
		log.Printf("[INFO] Gateway for %s from systemd-networkd: %s", iface.Name, *gw)
		return gw
	}

	log.Printf("[INFO] No gateway found for %s -- will configure SBR without a "+
		"default route in its table (subnet-only routing)", iface.Name)
	return nil
}

func gatewayFromExistingRoutes(iface *models.InterfaceInfo) *string {
	res, _ := exec.RunCommand("ip route show table all default", false, 10)
	for _, line := range strings.Split(res.Stdout, "\n") {
		if strings.Contains(line, fmt.Sprintf("dev %s", iface.Name)) {
			if m := reViaGw.FindStringSubmatch(line); m != nil {
				return &m[1]
			}
		}
	}
	return nil
}

func gatewayFromDHCPLeases(iface *models.InterfaceInfo) *string {
	for _, pattern := range constants.DHCPLeasePaths {
		path := strings.ReplaceAll(pattern, "{iface}", iface.Name)
		matches, _ := filepath.Glob(path)
		for _, leaseFile := range matches {
			content, err := exec.ReadFile(leaseFile)
			if err != nil || content == "" {
				continue
			}
			if m := reDHCPRouters.FindStringSubmatch(content); m != nil {
				return &m[1]
			}
			if m := reDHCPRouter2.FindStringSubmatch(content); m != nil {
				return &m[1]
			}
		}
	}
	return nil
}

func gatewayFromNmcli(iface *models.InterfaceInfo) *string {
	if !exec.CommandExists("nmcli") {
		return nil
	}
	res, err := exec.RunCommand(
		fmt.Sprintf("nmcli -t -f IP4.GATEWAY device show %s", iface.Name), false, 10)
	if err != nil || res.ExitCode != 0 {
		return nil
	}
	for _, line := range strings.Split(res.Stdout, "\n") {
		if strings.HasPrefix(line, "IP4.GATEWAY:") {
			gw := strings.TrimSpace(strings.SplitN(line, ":", 2)[1])
			if gw != "" && gw != "--" {
				return &gw
			}
		}
	}
	return nil
}

func gatewayFromNetworkd(iface *models.InterfaceInfo) *string {
	entries, err := os.ReadDir(constants.SystemdNetworkDir)
	if err != nil {
		return nil
	}
	// Sort entries for deterministic behavior.
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name() < entries[j].Name()
	})
	matchRe := regexp.MustCompile(`\[Match\]\s*\n\s*Name\s*=\s*` + regexp.QuoteMeta(iface.Name) + `\b`)
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".network") {
			continue
		}
		content, _ := exec.ReadFile(filepath.Join(constants.SystemdNetworkDir, entry.Name()))
		if content == "" {
			continue
		}
		if matchRe.MatchString(content) {
			if m := reGatewayKey.FindStringSubmatch(content); m != nil {
				return &m[1]
			}
		}
	}
	return nil
}

// -----------------------------------------------------------------------
// Network manager detection
// -----------------------------------------------------------------------

func detectNetworkManager() models.NetworkManagerType {
	// Check netplan first.
	if isDir(constants.NetplanDir) && exec.CommandExists("netplan") {
		matches, _ := filepath.Glob(filepath.Join(constants.NetplanDir, "*.yaml"))
		if len(matches) > 0 {
			renderer := detectNetplanRenderer(matches)
			if renderer == "NetworkManager" {
				log.Println("[INFO] Detected: netplan with NetworkManager renderer")
				return models.NMNetplanNM
			}
			log.Println("[INFO] Detected: netplan with systemd-networkd renderer")
			return models.NMNetplanNetworkd
		}
	}

	// Check NetworkManager.
	if serviceIsActive("NetworkManager.service") || serviceIsActive("NetworkManager") {
		log.Println("[INFO] Detected: NetworkManager")
		return models.NMNetworkManager
	}

	// Check systemd-networkd.
	if serviceIsActive("systemd-networkd.service") || serviceIsActive("systemd-networkd") {
		log.Println("[INFO] Detected: systemd-networkd")
		return models.NMSystemdNetworkd
	}

	// Check ifupdown.
	if fileExists(constants.InterfacesFile) && (exec.CommandExists("ifup") || exec.CommandExists("ifdown")) {
		log.Println("[INFO] Detected: ifupdown")
		return models.NMIfupdown
	}

	log.Println("[WARN] Could not detect network manager")
	return models.NMUnknown
}

func detectNetplanRenderer(yamlFiles []string) string {
	for _, path := range yamlFiles {
		content, _ := exec.ReadFile(path)
		if content == "" {
			continue
		}
		if m := reNetplanRend.FindStringSubmatch(content); m != nil {
			return m[1]
		}
	}
	return "networkd"
}

func serviceIsActive(service string) bool {
	res, _ := exec.RunCommand(fmt.Sprintf("systemctl is-active %s", service), false, 10)
	return strings.TrimSpace(res.Stdout) == "active"
}

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

func computeSubnet(ipAddr string, prefix int) string {
	cidr := fmt.Sprintf("%s/%d", ipAddr, prefix)
	_, network, err := net.ParseCIDR(cidr)
	if err != nil {
		return cidr
	}
	return network.String()
}

func toSet(ss []string) map[string]bool {
	m := make(map[string]bool, len(ss))
	for _, s := range ss {
		m[s] = true
	}
	return m
}

func containsStr(ss []string, target string) bool {
	for _, s := range ss {
		if s == target {
			return true
		}
	}
	return false
}

func jsonStr(data map[string]interface{}, key string) string {
	v, _ := data[key].(string)
	return v
}

func jsonInt(data map[string]interface{}, key string) int {
	v, _ := data[key].(float64)
	return int(v)
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
