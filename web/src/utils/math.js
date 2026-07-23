export function calculateRms(samples, channels = 8) {
  try {
    const safeChannels = Math.max(1, Number(channels) || 1)
    if (!Array.isArray(samples) || samples.length === 0) return 0

    let sumSquares = 0
    let denominator = 0

    if (Array.isArray(samples[0])) {
      const sampleCount = samples.length
      denominator = sampleCount * safeChannels
      for (let i = 0; i < sampleCount; i++) {
        const row = samples[i]
        for (let ch = 0; ch < safeChannels; ch++) {
          const v = Number(row?.[ch] ?? 0)
          sumSquares += v * v
        }
      }
    } else {
      const flat = samples
      const sampleCount = Math.max(1, Math.floor(flat.length / safeChannels))
      denominator = sampleCount * safeChannels
      for (let i = 0; i < Math.min(flat.length, denominator); i++) {
        const v = Number(flat[i] ?? 0)
        sumSquares += v * v
      }
    }

    if (denominator <= 0) return 0
    return Math.sqrt(sumSquares / denominator)
  } catch (error) {
    console.error('[math] calculateRms failed:', error)
    return 0
  }
}

export function normalizeStrength(rms) {
  try {
    const normalized = Math.round((Number(rms) || 0) / 10)
    return Math.min(100, Math.max(0, normalized))
  } catch (error) {
    console.error('[math] normalizeStrength failed:', error)
    return 0
  }
}

export function calculateStrength(samples, channels = 8) {
  const rms = calculateRms(samples, channels)
  return {
    rms,
    strength: normalizeStrength(rms),
  }
}
