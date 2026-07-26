# API Standards

## Base Path

All application APIs use:

```text
/api/v1
```

## Success Response Shape

Use a consistent response envelope:

```json
{
  "success": true,
  "message": "Operation completed successfully.",
  "data": {},
  "meta": {}
}
```

Rules:

- `data` contains the resource or result.
- `meta` is optional and used for pagination, filters, or request context.
- Use clear human-readable messages, but frontend behavior should depend on status codes and data, not message text.

## Error Response Shape

Use a consistent error envelope:

```json
{
  "success": false,
  "message": "Validation failed.",
  "error": {
    "code": "VALIDATION_ERROR",
    "details": []
  }
}
```

## Standard Error Codes

- `VALIDATION_ERROR`
- `AUTHENTICATION_REQUIRED`
- `INVALID_CREDENTIALS`
- `FORBIDDEN`
- `NOT_FOUND`
- `CONFLICT`
- `TENANT_ACCESS_DENIED`
- `MODULE_DISABLED`
- `RATE_LIMITED`
- `UPLOAD_INVALID`
- `AI_PROVIDER_FAILED`
- `INTERNAL_SERVER_ERROR`

## Pagination Shape

Paginated list APIs should return:

```json
{
  "success": true,
  "message": "Records fetched successfully.",
  "data": [],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 0,
    "totalPages": 0
  }
}
```

## Authentication

Business dashboard APIs use business auth JWTs.

Customer portal APIs use customer auth JWTs.

Admin APIs require:

- valid JWT
- `globalRole = "platform_admin"`

## Route Groups

Planned API groups:

- `/auth`
- `/customer/auth`
- `/tenants`
- `/modules`
- `/public`
- `/customer`
- `/admin`

## Public Visibility Rule

Public and marketplace endpoints may return a tenant only when:

```text
tenant.status = active
tenant.websiteStatus = published
tenant.settings.publicVisibility = true
```
