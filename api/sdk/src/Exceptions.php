<?php

namespace AgentMemory\Exceptions;

class AgentMemoryException extends \RuntimeException {}

class AuthenticationException extends AgentMemoryException {}

class MemoryNotFoundException extends AgentMemoryException {}
