# Database Setup for Postgres (pgvector)

This document outlines the database-side changes you need to make to use Postgres with pgvector instead of Milvus.

## Overview

The code has been updated to use Postgres with the pgvector extension. The Docker Compose file will automatically set up Postgres with pgvector, but you may need to perform some additional database setup steps.

## Database Setup Steps

### Option 1: Using Docker Compose (Recommended)

If you're using the provided `docker-compose.yaml`, the Postgres service is already configured with:
- Image: `pgvector/pgvector:pg16` (includes pgvector extension)
- Auto-loads the vector extension via `shared_preload_libraries=vector`

**What you need to do:**

1. **Start the services:**
   ```bash
   cd server
   docker compose up -d
   ```

2. **Verify Postgres is running:**
   ```bash
   docker compose ps
   ```

3. **Connect to Postgres and create the extension (if not auto-created):**
   ```bash
   docker compose exec postgres psql -U postgres -d postgres
   ```

4. **Inside the psql prompt, run:**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   \q
   ```

   **Note:** The docker-compose configuration should auto-load the extension, but running this command ensures it's available.

### Option 2: Using External Postgres Instance

If you're using an existing Postgres database (not Docker):

1. **Install pgvector extension:**
   
   **On Ubuntu/Debian:**
   ```bash
   sudo apt-get install postgresql-16-pgvector
   ```
   
   **On macOS (Homebrew):**
   ```bash
   brew install pgvector
   ```
   
   **On other systems or from source:**
   ```bash
   git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git
   cd pgvector
   make
   sudo make install
   ```

2. **Create the database (if it doesn't exist):**
   ```sql
   CREATE DATABASE postgres;  -- or your preferred database name
   ```

3. **Connect to your database:**
   ```bash
   psql -U postgres -d postgres
   ```

4. **Create the vector extension:**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

5. **Verify the extension is installed:**
   ```sql
   \dx vector
   ```
   
   You should see output showing the vector extension is installed.

6. **Update your environment variables** in `.env` file:
   ```bash
   POSTGRES_HOST=your-postgres-host
   POSTGRES_PORT=5432
   POSTGRES_USER=your-username
   POSTGRES_PASSWORD=your-password
   POSTGRES_DBNAME=your-database-name
   POSTGRES_COLLECTION_NAME=memories
   POSTGRES_EMBEDDING_DIMS=1536
   ```

### Option 3: Using Managed Postgres (AWS RDS, Google Cloud SQL, etc.)

For managed Postgres services:

1. **Enable the pgvector extension** in your managed database:
   
   **AWS RDS:**
   - pgvector is available on RDS for PostgreSQL 11+ 
   - Connect to your database and run:
     ```sql
     CREATE EXTENSION IF NOT EXISTS vector;
     ```
   
   **Google Cloud SQL:**
   - Enable the `vector` extension via Cloud Console or run:
     ```sql
     CREATE EXTENSION IF NOT EXISTS vector;
     ```
   
   **Azure Database for PostgreSQL:**
   - Enable the extension:
     ```sql
     CREATE EXTENSION IF NOT EXISTS vector;
     ```

2. **Update your environment variables** with the managed database connection details:
   ```bash
   POSTGRES_HOST=your-managed-db-host
   POSTGRES_PORT=5432
   POSTGRES_USER=your-username
   POSTGRES_PASSWORD=your-password
   POSTGRES_DBNAME=your-database-name
   POSTGRES_SSLMODE=require  # Usually required for managed databases
   ```

## Environment Variables

Update your `.env` file with the following Postgres variables (remove old Milvus variables):

```bash
# Postgres Configuration
POSTGRES_HOST=postgres          # or your Postgres host
POSTGRES_PORT=5432
POSTGRES_USER=postgres          # or your Postgres username
POSTGRES_PASSWORD="postgres"    # or your Postgres password (use quotes if password contains special characters)
POSTGRES_DBNAME=postgres        # or your database name
POSTGRES_COLLECTION_NAME=memories
POSTGRES_EMBEDDING_DIMS=1536

# Optional SSL configuration (for managed databases)
# POSTGRES_SSLMODE=require

# Optional: Use connection string instead of individual parameters
# POSTGRES_CONNECTION_STRING=postgresql://user:password@host:port/dbname
```

### Handling Passwords with Special Characters

If your password contains special characters like `#`, `&`, `!`, `$`, etc., you **must quote the password** in your `.env` file:

**❌ Incorrect (will be treated as comment):**
```bash
POSTGRES_PASSWORD=Td3#Mp6&Vr8!ThR
```

**✅ Correct (use double quotes):**
```bash
POSTGRES_PASSWORD="Td3#Mp6&Vr8!ThR"
```

**✅ Also correct (use single quotes):**
```bash
POSTGRES_PASSWORD='Td3#Mp6&Vr8!ThR'
```

**Note:** Both single and double quotes work. Double quotes allow variable expansion if needed, but for passwords, either works fine.

**Alternative: Using Connection String**

If you prefer, you can use a connection string instead (with URL-encoded password):

```bash
# URL-encode special characters: # = %23, & = %26, ! = %21
POSTGRES_CONNECTION_STRING="postgresql://postgres:Td3%23Mp6%26Vr8%21ThR@postgres:5432/postgres"
```

When using `POSTGRES_CONNECTION_STRING`, you don't need to set the individual `POSTGRES_HOST`, `POSTGRES_PORT`, etc. variables.

## Verification Steps

1. **Check Postgres is accessible:**
   ```bash
   # For Docker setup
   docker compose exec postgres pg_isready -U postgres
   
   # For external setup
   psql -h your-host -U your-user -d your-db -c "SELECT version();"
   ```

2. **Verify pgvector extension:**
   ```sql
   -- Connect to your database
   psql -U postgres -d postgres
   
   -- Check extension
   \dx vector
   
   -- Test vector type
   SELECT '[1,2,3]'::vector;
   ```

3. **Test the application:**
   ```bash
   # Start the application
   docker compose up
   
   # Check health endpoint
   curl http://localhost:8888/health
   ```

## Migration Notes

- **Data Migration:** If you have existing data in Milvus, you'll need to export it and re-import it into Postgres. The data structures are different between the two systems.

- **Performance:** pgvector with HNSW indexing (enabled by default) provides excellent performance for vector similarity search.

- **Indexing:** The application automatically creates HNSW indexes on the vector columns. No manual index creation is needed.

## Troubleshooting

### Extension not found error
```
ERROR: extension "vector" does not exist
```
**Solution:** Make sure you've run `CREATE EXTENSION IF NOT EXISTS vector;` in your database.

### Connection refused
```
could not connect to server: Connection refused
```
**Solution:** 
- Check Postgres is running: `docker compose ps` or `systemctl status postgresql`
- Verify host and port in environment variables
- Check firewall settings

### SSL connection required
```
SSL connection is required
```
**Solution:** Add `POSTGRES_SSLMODE=require` to your `.env` file (common for managed databases).

## Additional Resources

- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [mem0 pgvector Documentation](https://docs.mem0.ai/components/vectordbs/dbs/pgvector)

