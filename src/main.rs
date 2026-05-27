//! rustok-mcp — MCP server entry point.

use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "rustok-mcp")]
struct Cli {
    #[arg(long, default_value = "http")]
    transport: String,
    #[arg(long, default_value = "127.0.0.1")]
    host: String,
    #[arg(long, default_value = "3000")]
    port: u16,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .init();

    let _cli = Cli::parse();
    tracing::info!("rustok-mcp starting");

    // TODO: initialize core, start transport
}
