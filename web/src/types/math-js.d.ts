declare module '@/utils/math.js' {
  export function calculateRms(samples: number[][] | number[], channels?: number): number
  export function normalizeStrength(rms: number): number
  export function calculateStrength(
    samples: number[][] | number[],
    channels?: number,
  ): { rms: number; strength: number }
}
