export class RemembrError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
  ) {
    super(message);
    this.name = "RemembrError";
  }
}

export class AuthError extends RemembrError {
  constructor(message = "Invalid or expired agent token") {
    super(message, 401);
    this.name = "AuthError";
  }
}

export class NotFoundError extends RemembrError {
  constructor(message = "Resource not found") {
    super(message, 404);
    this.name = "NotFoundError";
  }
}

export class RateLimitError extends RemembrError {
  constructor(message = "Rate limit exceeded") {
    super(message, 429);
    this.name = "RateLimitError";
  }
}

export class ValidationError extends RemembrError {
  constructor(message = "Validation failed") {
    super(message, 422);
    this.name = "ValidationError";
  }
}
