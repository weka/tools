// sbr-config: Source-Based Routing Configuration Tool for multi-NIC Linux systems.
package main

import (
	"os"

	"github.com/weka/tools/preinstall/sbr-config/internal/cli"
)

// version is set at build time via -ldflags.
var version = "dev"

func main() {
	os.Exit(cli.Run(version, os.Args[1:]))
}
