/**
 * Register the server-only stub loader for Node (container smoke only).
 */
import { register } from "node:module";

register("./stub-server-only-loader.mjs", import.meta.url);
