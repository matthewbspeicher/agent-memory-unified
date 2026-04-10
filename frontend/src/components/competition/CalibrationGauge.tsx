// frontend/src/components/competition/CalibrationGauge.tsx
interface CalibrationGaugeProps {
  score: number;
  sampleSize?: number;
}

export function CalibrationGauge({ score, sampleSize }: CalibrationGaugeProps) {
  const color = score >= 0.8 ? 'var(--color-accent-success)' : score >= 0.6 ? 'var(--color-accent-warning)' : 'var(--color-accent-danger)';
  const label = score >= 0.8 ? 'Calibrated' : score >= 0.6 ? 'Drifting' : 'Unreliable';

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-500">Calibration</span>
        <span style={{ color }}>
          {label} ({(score * 100).toFixed(0)}%{sampleSize ? `, n=${sampleSize}` : ''})
        </span>
      </div>
      <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div 
          className="h-full rounded-full transition-all" 
          style={{ width: `${score * 100}%`, backgroundColor: color }} 
        />
      </div>
    </div>
  );
}
