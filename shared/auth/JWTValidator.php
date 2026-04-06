<?php

namespace Shared\Auth;

use Firebase\JWT\JWT;
use Firebase\JWT\Key;
use Predis\Client;

class JWTValidator
{
    private \Predis\Client|\Redis $redis;
    private string $secret;
    private string $algorithm;

    public function __construct(\Predis\Client|\Redis $redis, string $secret, string $algorithm = 'HS256')
    {
        $this->redis = $redis;
        $this->secret = $secret;
        $this->algorithm = $algorithm;
    }

    /**
     * Validate JWT and check Redis blacklist.
     *
     * @throws \Exception if token invalid or revoked
     */
    public function validate(string $token): array
    {
        try {
            // Decode and verify JWT
            $payload = JWT::decode($token, new Key($this->secret, $this->algorithm));
            $payloadArray = (array) $payload;

            // Check Redis blacklist
            $userId = $payloadArray['sub'];

            // Check wildcard revocation (all tokens for user)
            $wildcardRevoked = $this->redis->sismember("revoked_tokens:{$userId}", '*');
            if ($wildcardRevoked) {
                throw new \Exception('Token revoked (wildcard)');
            }

            // Check specific token revocation
            $tokenRevoked = $this->redis->sismember("revoked_tokens:{$userId}", $token);
            if ($tokenRevoked) {
                throw new \Exception('Token revoked (specific)');
            }

            return $payloadArray;

        } catch (\Firebase\JWT\ExpiredException $e) {
            throw new \Exception('Token expired');
        } catch (\Firebase\JWT\SignatureInvalidException $e) {
            throw new \Exception('Invalid token signature');
        } catch (\Firebase\JWT\BeforeValidException $e) {
            throw new \Exception('Token not yet valid');
        }
    }

    /**
     * Issue a new JWT for a user/agent.
     */
    public function issue(string $subject, string $type, array $scopes, int $expiryMinutes = 15): string
    {
        $payload = [
            'sub' => $subject,
            'type' => $type,  // 'user' or 'agent'
            'scopes' => $scopes,
            'iat' => time(),
            'exp' => time() + ($expiryMinutes * 60),
        ];

        return JWT::encode($payload, $this->secret, $this->algorithm);
    }
}
