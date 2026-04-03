export class RemembrError extends Error {
  public readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'RemembrError';
    this.status = status;
  }
}

export class AuthenticationError extends RemembrError {
  constructor(message = 'Invalid or inactive agent token') {
    super(message, 401);
    this.name = 'AuthenticationError';
  }
}

export class NotFoundError extends RemembrError {
  constructor(message = 'Memory not found') {
    super(message, 404);
    this.name = 'NotFoundError';
  }
}

export class ValidationError extends RemembrError {
  public readonly errors: Record<string, string[]>;

  constructor(message: string, errors: Record<string, string[]> = {}) {
    super(message, 422);
    this.name = 'ValidationError';
    this.errors = errors;
  }
}

export class RateLimitError extends RemembrError {
  public readonly retryAfter: number | null;

  constructor(retryAfter: number | null = null) {
    super('Rate limit exceeded', 429);
    this.name = 'RateLimitError';
    this.retryAfter = retryAfter;
  }
}
