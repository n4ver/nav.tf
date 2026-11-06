export async function pollUntil(predicate, { timeoutMs = 10000, intervalMs = 300 } = {}) {
  const deadline = Date.now() + timeoutMs
  let result
  while (Date.now() < deadline) {
    result = await predicate()
    if (result) return result
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return result
}
