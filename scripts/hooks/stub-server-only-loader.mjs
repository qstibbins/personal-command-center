/**
 * Node custom loader: resolve `server-only` to a no-op stub.
 * Used only by production-container application-path verification.
 */

const stubUrl = new URL("./server-only-stub.mjs", import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "server-only") {
    return { shortCircuit: true, url: stubUrl };
  }
  return nextResolve(specifier, context);
}
