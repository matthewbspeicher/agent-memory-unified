import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GlassCard } from './GlassCard';

describe('GlassCard', () => {
  it('renders children', () => {
    render(<GlassCard>Test content</GlassCard>);
    expect(screen.getByText('Test content')).toBeDefined();
  });

  it('renders with default variant', () => {
    const { container } = render(<GlassCard>Default</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-white/10');
  });

  it('renders with cyan variant', () => {
    const { container } = render(<GlassCard variant="cyan">Cyan</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-cyan-500/30');
  });

  it('renders with violet variant', () => {
    const { container } = render(<GlassCard variant="violet">Violet</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-violet-500/30');
  });

  it('renders with green variant', () => {
    const { container } = render(<GlassCard variant="green">Green</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-emerald-500/30');
  });

  it('renders with red variant', () => {
    const { container } = render(<GlassCard variant="red">Red</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-rose-500/30');
  });

  it('applies custom className', () => {
    const { container } = render(<GlassCard className="custom-class">Custom</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('custom-class');
  });

  it('disables hover effect when hoverEffect is false', () => {
    const { container } = render(<GlassCard hoverEffect={false}>No hover</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).not.toContain('hover:-translate-y-1');
  });

  it('passes through HTML attributes', () => {
    const { container } = render(<GlassCard data-testid="test-card">Attrs</GlassCard>);
    expect(container.firstChild).toHaveAttribute('data-testid', 'test-card');
  });

  it('has glassmorphism styling', () => {
    const { container } = render(<GlassCard>Glass</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('backdrop-blur-md');
    expect(card.className).toContain('bg-slate-950/40');
  });
});
