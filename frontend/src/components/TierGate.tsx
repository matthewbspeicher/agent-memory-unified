import React from 'react';

export type Tier = 'explorer' | 'trader' | 'enterprise' | 'whale';

const TIER_LEVELS: Record<Tier, number> = {
  explorer: 0,
  trader: 1,
  enterprise: 2,
  whale: 3,
};

interface TierGateProps {
  requiredTier: Tier;
  userTier: Tier;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export const TierGate: React.FC<TierGateProps> = ({ requiredTier, userTier, children, fallback }) => {
  if (TIER_LEVELS[userTier] >= TIER_LEVELS[requiredTier]) {
    return <>{children}</>;
  }
  return <>{fallback}</>;
};
