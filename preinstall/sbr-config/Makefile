MODULE   := github.com/weka/tools/preinstall/sbr-config
BINARY   := sbr-config
CMD_DIR  := ./cmd/sbr-config
VERSION  ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS  := -s -w -X main.version=$(VERSION)

.PHONY: build release clean fmt vet test tidy

# Dev build (local platform).
build: tidy
	go build -ldflags "$(LDFLAGS)" -o $(BINARY) $(CMD_DIR)
	@echo "Built $(BINARY) $(VERSION)"

# Release build: static linux/amd64 binary.
release: tidy
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
		go build -ldflags "$(LDFLAGS)" -o $(BINARY) $(CMD_DIR)
	@echo "Built static $(BINARY) $(VERSION) (linux/amd64)"

clean:
	rm -f $(BINARY)

fmt:
	gofmt -s -w .

vet:
	go vet ./...

test:
	go test ./...

tidy:
	go mod tidy
