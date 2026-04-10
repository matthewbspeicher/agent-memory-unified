import { cn } from '../../lib/utils';

type AlertType = 'success' | 'error' | 'warning' | 'info';

interface AlertCardProps {
  type: AlertType;
  title: string;
  message: string;
  timestamp?: string;
  onDismiss?: () => void;
}

const alertStyles: Record<AlertType, string> = {
  success: 'trading-alert-success',
  error: 'trading-alert-error',
  warning: 'trading-alert-warning',
  info: 'trading-alert-info',
};

const alertIcons: Record<AlertType, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
};

export function AlertCard({
  type,
  title,
  message,
  timestamp,
  onDismiss,
}: AlertCardProps) {
  return (
    <div className={cn('trading-alert', alertStyles[type])}>
      <div className="flex items-start gap-3">
        <span className="text-lg">{alertIcons[type]}</span>
        <div className="flex-1">
          <h4 className="font-semibold text-text-primary">{title}</h4>
          <p className="text-text-secondary text-sm mt-1">{message}</p>
          {timestamp && (
            <p className="text-text-muted text-xs mt-2">{timestamp}</p>
          )}
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-text-muted hover:text-text-primary transition-colors"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
