import { main } from "./spec-review/cli.ts";

process.exitCode = await main(process.argv.slice(2));
