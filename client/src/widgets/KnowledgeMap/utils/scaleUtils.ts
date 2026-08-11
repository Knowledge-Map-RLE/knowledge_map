export interface ScaleUnit {
    symbol: string;
    exponent: number;
    factor: number;
}

export const SCALE_UNITS: ScaleUnit[] = [
    { symbol: 'мм', exponent: -3, factor: 0.001 },
    { symbol: 'см', exponent: -2, factor: 0.01 },
    { symbol: 'дм', exponent: -1, factor: 0.1 },
    { symbol: 'м', exponent: 0, factor: 1 },
    { symbol: 'км', exponent: 3, factor: 1000 },
];

export function readableScaleToExponent(value: number, unit: ScaleUnit): number {
    if (value <= 0) return 0;
    return Math.round(Math.log10(value * unit.factor));
}

export function exponentToReadableScale(exponent: number): { value: number; unit: ScaleUnit } {
    if (exponent <= SCALE_UNITS[0].exponent) {
        return { value: 1, unit: SCALE_UNITS[0] };
    }
    let unit = SCALE_UNITS[0];
    for (const candidate of SCALE_UNITS) {
        if (candidate.exponent <= exponent) {
            unit = candidate;
        } else {
            break;
        }
    }
    return { value: Math.pow(10, exponent - unit.exponent), unit };
}

export function getLevelName(physicalScale: number): string {
    const { value, unit } = exponentToReadableScale(physicalScale);
    return `${value}${unit.symbol}`;
}
