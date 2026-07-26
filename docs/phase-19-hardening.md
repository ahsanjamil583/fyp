# Phase 19 Hardening

Phase 19 focuses on release-quality safeguards for the MVP:

- backend unit and API smoke tests
- tenant isolation rule verification
- auth and AI rule verification
- structured backend logging
- local backup support
- production safety checks in configuration

## Backend Test Command

Run the backend Phase 19 suite:

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py" -v
```

## Frontend Verification

Run the frontend production build smoke check:

```bash
cd frontend
npm run build
```

## Backup Command

Create a JSON backup of the main MongoDB collections:

```bash
cd backend
python scripts/backup_mongo.py
```

Optional custom output directory:

```bash
cd backend
python scripts/backup_mongo.py --output-dir ./backups
```

## Production Safety Rules

- `APP_ENV=production` requires `DEBUG=false`
- `JWT_SECRET_KEY` must not use the default placeholder value
- `BCRYPT_ROUNDS` should stay at `12` or higher
- backend logs are written to `LOG_DIR/backend.log`

## Coverage Focus

The current Phase 19 suite checks:

- health API availability
- token creation and auth guard behavior
- tenant ownership logic
- transaction workflow rules
- custom field validation rules
- Roman Urdu and Pakistan-first localization rules
- AI draft-order and intent logic
