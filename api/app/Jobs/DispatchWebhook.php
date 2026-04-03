<?php

namespace App\Jobs;

use App\Models\WebhookDelivery;
use App\Models\WebhookSubscription;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class DispatchWebhook implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public $tries = 3;

    private const BLOCKED_IP_RANGES = [
        '10.0.0.0/8',
        '172.16.0.0/12',
        '192.168.0.0/16',
        '127.0.0.0/8',
        '169.254.0.0/16',
        '0.0.0.0/8',
        '::1/128',
        'fc00::/7',
        'fe80::/10',
    ];

    public function backoff()
    {
        return [10, 60, 300];
    }

    public function __construct(
        public WebhookSubscription $subscription,
        public string $event,
        public array $payload
    ) {}

    public function handle(): void
    {
        if (! $this->subscription->is_active) {
            return;
        }

        if (! $this->isUrlSafe($this->subscription->url)) {
            $this->subscription->update(['is_active' => false]);

            return;
        }

        $body = [
            'id' => Str::uuid()->toString(),
            'event' => $this->event,
            'timestamp' => now()->toIso8601String(),
            'data' => $this->payload,
        ];

        $jsonBody = json_encode($body);

        $signature = hash_hmac('sha256', $jsonBody, $this->subscription->secret);

        try {
            $response = Http::withHeaders([
                'Content-Type' => 'application/json',
                'Webhook-Signature' => $signature,
                'User-Agent' => 'Remembr-Webhook/1.0',
            ])->timeout(5)->withBody($jsonBody, 'application/json')->post($this->subscription->url);

            $status = $response->status();
            $failed = $response->failed();
        } catch (\Exception $e) {
            $status = null;
            $failed = true;
        }

        WebhookDelivery::create([
            'subscription_id' => $this->subscription->id,
            'event' => $this->event,
            'payload' => $body,
            'response_status' => $status,
            'attempt' => $this->attempts(),
        ]);

        if ($failed) {
            $this->subscription->increment('failure_count');
            $this->subscription->refresh();

            if ($this->subscription->failure_count >= 10) {
                $this->subscription->update(['is_active' => false]);
            }

            if (isset($response)) {
                $response->throw();
            } else {
                throw $e;
            }
        } else {
            $this->subscription->update(['failure_count' => 0]);
        }
    }

    private function isUrlSafe(string $url): bool
    {
        $host = parse_url($url, PHP_URL_HOST);
        if (! $host) {
            return false;
        }

        $ips = gethostbynamel($host);
        if ($ips === false) {
            return false;
        }

        foreach ($ips as $ip) {
            if ($this->isPrivateIp($ip)) {
                return false;
            }
        }

        return true;
    }

    private function isPrivateIp(string $ip): bool
    {
        foreach (self::BLOCKED_IP_RANGES as $range) {
            if ($this->ipInRange($ip, $range)) {
                return true;
            }
        }

        return false;
    }

    private function ipInRange(string $ip, string $cidr): bool
    {
        if (str_contains($cidr, ':') !== str_contains($ip, ':')) {
            return false;
        }

        [$subnet, $bits] = explode('/', $cidr);

        if (str_contains($ip, ':')) {
            $ipBin = inet_pton($ip);
            $subnetBin = inet_pton($subnet);
            if ($ipBin === false || $subnetBin === false) {
                return false;
            }
            $mask = str_repeat("\xff", (int) ($bits / 8)).($bits % 8 ? chr(256 - (1 << (8 - $bits % 8))) : '');
            $mask = str_pad($mask, 16, "\0");

            return ($ipBin & $mask) === ($subnetBin & $mask);
        }

        $ipLong = ip2long($ip);
        $subnetLong = ip2long($subnet);
        $mask = -1 << (32 - (int) $bits);

        return ($ipLong & $mask) === ($subnetLong & $mask);
    }
}
