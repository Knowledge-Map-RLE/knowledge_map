export interface ScaleUnit {
    name: string;
    exponent: number;
    factor: number;
}

export const SCALE_UNITS: ScaleUnit[] = [
    { name: 'мм', exponent: -3, factor: 0.001 },
    { name: 'см', exponent: -2, factor: 0.01 },
    { name: 'дм', exponent: -1, factor: 0.1 },
    { name: 'м', exponent: 0, factor: 1 },
    { name: 'км', exponent: 3, factor: 1000 },
];

export function readableScaleToExponent(scale: number): number {
    if (scale <= 0) return 0;
    return Math.round(Math.log10(scale));
}

export function exponentToReadableScale(exponent: number): number {
    return Math.pow(10, exponent);
}

export function getLevelName(physicalScale: number): string {
    if (physicalScale <= 0) return '1м';
    
    const exponent = readableScaleToExponent(physicalScale);
    const unit = SCALE_UNITS.find(u => u.exponent === exponent);
    
    if (unit) {
        return `1${unit.name}`;
    }
    
    return `${physicalScale}м`;
}
