---
name: security-review
description: Comprehensive security review checklist for code handling authentication, user input, secrets, API endpoints, payments, or sensitive data. ALWAYS use this skill when implementing auth, handling user input or file uploads, creating API endpoints, working with secrets or credentials, implementing payment features, storing or transmitting sensitive data, or when the user says "is this secure", "security review", "check for vulnerabilities", or "harden this".
---

# Security Review

Ensure code follows security best practices and identify potential vulnerabilities before they ship. Security issues found in review cost 100x less than security issues found in production.

## Security Checklist

### 1. Secrets Management
- No hardcoded API keys, tokens, or passwords — ever
- All secrets in environment variables or a secrets manager
- `.env` / `.env.local` in `.gitignore`
- No secrets in git history (check with `git log --all -S "API_KEY"`)

### 2. Input Validation
- All user inputs validated with schemas (Zod, Pydantic, etc.)
- File uploads restricted by size, type, and extension
- No direct use of user input in queries or commands
- Whitelist validation preferred over blacklist
- Error messages don't leak internal details

### 3. SQL Injection Prevention
- All queries parameterized — NEVER concatenate user input into SQL
- ORM/query builder used correctly (no raw queries with interpolation)

### 4. Authentication & Authorization
- Tokens in httpOnly cookies (not localStorage)
- Authorization checks before every sensitive operation
- Row Level Security enabled (if using Supabase/Postgres)
- Role-based access control implemented and tested

### 5. XSS Prevention
- User-provided HTML sanitized (DOMPurify or equivalent)
- Content Security Policy headers configured
- No dangerouslySetInnerHTML with user content

### 6. CSRF Protection
- CSRF tokens on all state-changing operations
- SameSite=Strict on session cookies

### 7. Rate Limiting
- Rate limiting on all public API endpoints
- Stricter limits on auth endpoints (login, signup, password reset)
- IP-based + user-based rate limiting layers

### 8. Sensitive Data Exposure
- No passwords, tokens, or PII in logs
- Error messages generic for end users, detailed in server logs only
- No stack traces exposed to clients
- Sensitive fields excluded from API responses by default

### 9. Dependency Security
- `npm audit` / `pip audit` clean or issues acknowledged
- No known critical vulnerabilities in dependencies
- Lock files committed and reviewed

### 10. API Security
- HTTPS enforced in production
- CORS properly configured (not `*` in production)
- Security headers set: CSP, X-Frame-Options, X-Content-Type-Options
- API versioning for breaking changes

## Pre-Deployment Checklist

- [ ] Secrets: all in env vars, none in code or git history
- [ ] Input validation: all inputs validated with schemas
- [ ] SQL injection: all queries parameterized
- [ ] XSS: user content sanitized
- [ ] CSRF: protection enabled on state-changing endpoints
- [ ] Auth: proper token handling, no localStorage for sessions
- [ ] Authorization: role checks on every protected route
- [ ] Rate limiting: enabled on all public endpoints
- [ ] HTTPS: enforced
- [ ] Security headers: CSP, X-Frame-Options configured
- [ ] Error handling: no sensitive data in client-facing errors
- [ ] Logging: no sensitive data logged
- [ ] Dependencies: audited
- [ ] CORS: properly scoped
- [ ] File uploads: validated and sandboxed

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) security-review skill
