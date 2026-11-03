/** Rounds a maximum up to a clean axis top with evenly spaced integer ticks. */
export function niceTicks(maxValue: number, targetCount = 4): number[] {
  if (!Number.isFinite(maxValue) || maxValue <= 0) return [0, 1];
  const rawStep = maxValue / targetCount;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const niceResidual = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  const step = Math.max(1, niceResidual * magnitude);
  const top = Math.ceil(maxValue / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top + step / 2; value += step) ticks.push(value);
  return ticks;
}
