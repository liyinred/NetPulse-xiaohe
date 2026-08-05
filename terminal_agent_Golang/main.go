package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"netpulse/terminal-agent/internal/app"
)

// main 初始化 Agent，并在收到退出信号时取消当前运行流程。
//
// 参数: 无。
// 返回值: 无。
func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := app.Run(ctx, os.Stdin, os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "Agent 运行失败: %v\n", err)
		os.Exit(1)
	}
}
