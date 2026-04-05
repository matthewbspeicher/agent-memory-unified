<?php

namespace Shared\Auth\Tests;

use PHPUnit\Framework\TestCase;
use Shared\Auth\JWTValidator;
use Firebase\JWT\JWT;
use Predis\Client;

class JWTValidatorTest extends TestCase
{
    private $validator;
    private $redis;
    private $secret = 'test-secret-key-for-testing-only-256-bits-long';

    protected function setUp(): void
    {
        $this->redis = $this->getMockBuilder(Client::class)
            ->disableOriginalConstructor()
            ->addMethods(['sismember'])
            ->getMock();
        $this->validator = new JWTValidator($this->redis, $this->secret);
    }

    public function test_validates_valid_jwt()
    {
        $payload = [
            'sub' => 'agent-123',
            'type' => 'agent',
            'scopes' => ['memories:write', 'trading:execute'],
            'iat' => time(),
            'exp' => time() + 900,
        ];

        $token = JWT::encode($payload, $this->secret, 'HS256');

        // Redis returns false (not revoked)
        $this->redis->method('sismember')->willReturn(0);

        $result = $this->validator->validate($token);

        $this->assertEquals('agent-123', $result['sub']);
        $this->assertEquals('agent', $result['type']);
        $this->assertContains('memories:write', $result['scopes']);
    }

    public function test_rejects_expired_jwt()
    {
        $payload = [
            'sub' => 'agent-123',
            'exp' => time() - 3600,  // Expired 1 hour ago
        ];

        $token = JWT::encode($payload, $this->secret, 'HS256');

        $this->expectException(\Exception::class);
        $this->expectExceptionMessage('Token expired');

        $this->validator->validate($token);
    }

    public function test_rejects_revoked_jwt_wildcard()
    {
        $payload = [
            'sub' => 'agent-123',
            'exp' => time() + 900,
        ];

        $token = JWT::encode($payload, $this->secret, 'HS256');

        // Redis returns true for wildcard revocation
        $this->redis->method('sismember')
            ->with('revoked_tokens:agent-123', '*')
            ->willReturn(1);

        $this->expectException(\Exception::class);
        $this->expectExceptionMessage('Token revoked');

        $this->validator->validate($token);
    }

    public function test_rejects_revoked_jwt_specific()
    {
        $payload = [
            'sub' => 'agent-123',
            'exp' => time() + 900,
        ];

        $token = JWT::encode($payload, $this->secret, 'HS256');

        // Redis returns false for wildcard, true for specific token
        $this->redis->method('sismember')
            ->willReturnCallback(function ($key, $member) use ($token) {
                if ($member === '*') return 0;
                if ($member === $token) return 1;
                return 0;
            });

        $this->expectException(\Exception::class);
        $this->expectExceptionMessage('Token revoked');

        $this->validator->validate($token);
    }
}
