# Full-Stack Best Practices Guide
## Essential Concepts for Optimized, Scalable, Secure, and Maintainable Applications

This document extracts the most important architectural patterns, design principles, and implementation strategies from our codebase that should be applied to **all full-stack projects** to ensure they are optimized, scalable, consistent, secure, modularized, and have minimal overhead.

---

## Table of Contents

1. [Architecture Patterns](#architecture-patterns)
2. [Code Organization & Reusability](#code-organization--reusability)
3. [Performance Optimization](#performance-optimization)
4. [Security Best Practices](#security-best-practices)
5. [Database Optimization](#database-optimization)
6. [API Design](#api-design)
7. [Error Handling & Logging](#error-handling--logging)
8. [Testing Strategy](#testing-strategy)
9. [Scalability Patterns](#scalability-patterns)
10. [Modern JavaScript/TypeScript Practices](#modern-javascripttypescript-practices)
11. [React 19 Built-in Hooks](#react-19-built-in-hooks)
12. [Zustand State Management Issues](#zustand-state-management-issues)
13. [XSS Protection](#xss-protection)
14. [Preventing Multiple API Calls](#preventing-multiple-api-calls)
15. [Duplicate Code Patterns](#duplicate-code-patterns)
16. [SOLID Principles and Object Oriented Programming](#solid-principles)
17. [Design Patterns](#design-patterns)
18. [Implementation Checklist & Summary](#implementation-checklist--summary)

---

## Architecture Patterns

### 1. Event-Driven Architecture (EDA)

**Why:** Decouples services, enables extensibility, improves maintainability, and follows SOLID principles.

**Implementation:**
```typescript
// Centralized Event Emitter
class EventEmitter {
  private listeners: Map<string, Function[]> = new Map();
  
  on(event: string, handler: Function) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event)!.push(handler);
  }
  
  emit(event: string, data: unknown) {
    const handlers = this.listeners.get(event) || [];
    handlers.forEach(handler => {
      try {
        handler(data);
      } catch (error) {
        console.error(`Error in event handler for ${event}:`, error);
      }
    });
  }
}

// Usage: Services emit events instead of calling other services directly
class UserService {
  async createUser(data: UserData) {
    const user = await this.save(data);
    
    // Emit event - don't care who listens
    eventEmitter.emit(USER_EVENTS.CREATED, {
      userId: user.id,
      email: user.email,
    });
    
    return user;
  }
}

// Listeners handle cross-cutting concerns
eventEmitter.on(USER_EVENTS.CREATED, (event) => {
  emailService.sendWelcome(event);
});

eventEmitter.on(USER_EVENTS.CREATED, (event) => {
  activityService.log(event);
});
```

**Benefits:**
- ✅ Single Responsibility Principle
- ✅ Open/Closed Principle (extend without modifying)
- ✅ Loose coupling
- ✅ Easy to test
- ✅ Centralized cross-cutting concerns

---

### 2. Repository Pattern

**Why:** Abstracts data access, improves testability, enables easy database switching, and centralizes query logic.

**Implementation:**
```typescript
// Base Repository
abstract class BaseRepository<T> {
  protected model: Model<T>;
  
  async findAll(filters?: Record<string, unknown>): Promise<T[]> {
    return this.model.find(filters).lean();
  }
  
  async findById(id: string): Promise<T | null> {
    return this.model.findById(id).lean();
  }
  
  async create(data: Partial<T>): Promise<T> {
    return this.model.create(data);
  }
  
  async update(id: string, data: Partial<T>): Promise<T | null> {
    return this.model.findByIdAndUpdate(id, data, { new: true }).lean();
  }
  
  async delete(id: string): Promise<boolean> {
    const result = await this.model.findByIdAndDelete(id);
    return !!result;
  }
}

// Specific Repository
class UserRepository extends BaseRepository<User> {
  constructor() {
    super(UserModel);
  }
  
  async findByEmail(email: string): Promise<User | null> {
    return this.model.findOne({ email }).lean();
  }
}

// Service uses Repository
class UserService {
  constructor(private repository: UserRepository) {}
  
  async getUser(id: string): Promise<User | null> {
    return this.repository.findById(id);
  }
}
```

**Benefits:**
- ✅ Testability (easy to mock)
- ✅ Database abstraction
- ✅ Centralized query logic
- ✅ Consistent data access patterns

---

### 3. Service Layer Pattern

**Why:** Separates business logic from API routes, improves reusability, and makes code testable.

**Implementation:**
```typescript
// Route handler (thin layer)
export async function POST(request: NextRequest) {
  const authResult = await getAuthenticatedSession();
  if (isAuthError(authResult)) return authResult;
  
  const body = await request.json();
  const service = new UserService();
  const user = await service.createUser(body);
  
  return NextResponse.json({ success: true, data: user });
}

// Service (business logic)
class UserService {
  async createUser(data: CreateUserData): Promise<User> {
    // Validation
    this.validateUserData(data);
    
    // Business logic
    const hashedPassword = await this.hashPassword(data.password);
    
    // Data access
    const user = await this.repository.create({
      ...data,
      password: hashedPassword,
    });
    
    // Events
    eventEmitter.emit(USER_EVENTS.CREATED, { userId: user.id });
    
    return user;
  }
}
```

**Benefits:**
- ✅ Separation of concerns
- ✅ Reusable business logic
- ✅ Easy to test
- ✅ Clean API routes

---

## Code Organization & Reusability

### 4. Utility Functions Library

**Why:** Eliminates code duplication, ensures consistency, and reduces maintenance overhead.

**Essential Utilities:**

#### API Helpers
```typescript
// Error handling
export function getErrorMessage(error: unknown, defaultMessage = "Unknown error"): string {
  return error instanceof Error ? error.message : defaultMessage;
}

// Response creation
export function createUnauthorizedResponse(): NextResponse {
  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

export function createForbiddenResponse(): NextResponse {
  return NextResponse.json({ error: "Forbidden" }, { status: 403 });
}

export function createNotFoundResponse(resource: string): NextResponse {
  return NextResponse.json({ error: `${resource} not found` }, { status: 404 });
}

// Authentication
export function isAuthError(authResult: unknown): authResult is NextResponse {
  return authResult instanceof NextResponse;
}

export async function isAdminUser(userId: string): Promise<boolean> {
  const { checkApiPermissions, PERMISSIONS } = await import("@/lib/server-permissions");
  return checkApiPermissions(userId, [PERMISSIONS.ADMIN_ACCESS]);
}
```

#### Data Helpers
```typescript
// ID extraction
export function extractId(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "_id" in value) {
    return String((value as { _id: unknown })._id);
  }
  return String(value ?? "");
}

// Array normalization
export function normalizeToArray<T>(
  result: T[] | { data: T[] } | null | undefined
): T[] {
  if (!result) return [];
  if (Array.isArray(result)) return result;
  if (typeof result === "object" && "data" in result && Array.isArray(result.data)) {
    return result.data;
  }
  return [];
}

// Date formatting
export function toIsoString(value: unknown): string {
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "string" && value.trim()) return value;
  return new Date().toISOString();
}
```

#### Query Helpers
```typescript
// Safe parsing
export function parseIntSafe(value: string | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? undefined : parsed;
}

export function parseBooleanSafe(value: string | null | undefined): boolean | undefined {
  if (value === null || value === undefined) return undefined;
  if (value.toLowerCase() === "true") return true;
  if (value.toLowerCase() === "false") return false;
  return undefined;
}
```

**Benefits:**
- ✅ 90%+ reduction in duplicate code
- ✅ Consistent behavior across codebase
- ✅ Easy to update patterns globally
- ✅ Better type safety

---

## Performance Optimization

### 5. Database Aggregation Pipelines

**Why:** Eliminates N+1 queries, reduces database round trips, and improves performance.

**Implementation:**
```typescript
// ❌ Bad: N+1 Query Problem
async getUsersWithRoles() {
  const users = await User.find();
  for (const user of users) {
    user.role = await Role.findById(user.roleId); // N queries!
  }
  return users;
}

// ✅ Good: Aggregation Pipeline
async getUsersWithRoles() {
  return User.aggregate([
    {
      $lookup: {
        from: "roles",
        localField: "roleId",
        foreignField: "_id",
        as: "role"
      }
    },
    { $unwind: { path: "$role", preserveNullAndEmptyArrays: true } }
  ]);
}
```

**Benefits:**
- ✅ Single database query
- ✅ Better performance
- ✅ Scalable to large datasets

---

### 6. Pagination

**Why:** Prevents loading excessive data, reduces memory usage, and improves response times.

**Implementation:**
```typescript
async getAll(
  filters?: Filters,
  options?: { limit?: number; skip?: number; sort?: Record<string, 1 | -1> }
): Promise<{ data: T[]; total: number; page: number; pageSize: number }> {
  const query = this.buildQuery(filters);
  const limit = options?.limit ?? 50;
  const skip = options?.skip ?? 0;
  const sort = options?.sort ?? { createdAt: -1 };
  
  const [data, total] = await Promise.all([
    this.model.find(query).sort(sort).limit(limit).skip(skip).lean(),
    this.model.countDocuments(query)
  ]);
  
  return {
    data: data as T[],
    total,
    page: Math.floor(skip / limit) + 1,
    pageSize: limit
  };
}
```

**Benefits:**
- ✅ Prevents memory issues
- ✅ Faster API responses
- ✅ Better user experience

---

### 7. Caching Strategy

**Why:** Reduces database load, improves response times, and enhances user experience.

**Implementation:**
```typescript
// HTTP Response Caching
class CacheManager {
  private cache: Map<string, CacheEntry> = new Map();
  
  async get<T>(key: string, fetcher: () => Promise<T>, ttl = 300): Promise<T> {
    const cached = this.cache.get(key);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.data as T;
    }
    
    const data = await fetcher();
    this.cache.set(key, {
      data,
      expiresAt: Date.now() + ttl * 1000
    });
    
    return data;
  }
  
  invalidate(pattern: string) {
    for (const key of this.cache.keys()) {
      if (key.includes(pattern)) {
        this.cache.delete(key);
      }
    }
  }
}

// Usage in API routes
const data = await cacheManager.get(
  `users:${userId}`,
  () => userService.getById(userId),
  300 // 5 minutes
);
```

**Benefits:**
- ✅ Reduced database load
- ✅ Faster responses
- ✅ Better scalability

---

### 8. Batch API

**Why:** Reduces network round trips, improves performance, and enhances user experience.

**Implementation:**
```typescript
// POST /api/batch
export async function POST(request: NextRequest) {
  const { requests } = await request.json();
  
  // Execute requests in parallel
  const responses = await Promise.all(
    requests.map(async (req: BatchRequest) => {
      try {
        const result = await executeRequest(req);
        return { id: req.id, success: true, data: result };
      } catch (error) {
        return { id: req.id, success: false, error: getErrorMessage(error) };
      }
    })
  );
  
  return NextResponse.json({ success: true, responses });
}

// Client usage
const result = await batchApiService.execute([
  { id: "users", path: "/api/users", method: "GET" },
  { id: "roles", path: "/api/roles", method: "GET" },
]);
```

**Benefits:**
- ✅ 50-70% reduction in network overhead
- ✅ Faster page loads
- ✅ Better user experience

---

### 9. Job Queue for Long-Running Tasks

**Why:** Prevents API timeouts, enables background processing, and improves user experience.

**Implementation:**
```typescript
// Job Queue Service
class JobQueueService {
  async add(
    type: JobType,
    payload: Record<string, unknown>,
    userId: string
  ): Promise<string> {
    const job = await Job.create({
      type,
      status: JobStatus.PENDING,
      data: { payload, userId },
      createdAt: new Date()
    });
    
    eventEmitter.emit(JOB_EVENTS.CREATED, { jobId: job._id, type, userId });
    return job._id.toString();
  }
  
  async getStatus(jobId: string): Promise<JobStatus | null> {
    const job = await Job.findById(jobId);
    return job?.status || null;
  }
}

// API Route
export async function POST(request: NextRequest) {
  const { targetUserId } = await request.json();
  
  // Queue job instead of processing synchronously
  const jobId = await jobQueue.add(
    JobType.CALCULATE_INCENTIVES,
    { targetUserId },
    userId
  );
  
  // Return immediately
  return NextResponse.json({
    success: true,
    jobId,
    status: "pending"
  });
}

// Background processor
class JobProcessor {
  async process() {
    const job = await Job.findOne({ status: JobStatus.PENDING });
    if (!job) return;
    
    await Job.findByIdAndUpdate(job._id, { status: JobStatus.PROCESSING });
    
    try {
      const result = await this.executeJob(job);
      await Job.findByIdAndUpdate(job._id, {
        status: JobStatus.COMPLETED,
        result
      });
    } catch (error) {
      await Job.findByIdAndUpdate(job._id, {
        status: JobStatus.FAILED,
        error: getErrorMessage(error)
      });
    }
  }
}
```

**Benefits:**
- ✅ Non-blocking API responses
- ✅ Automatic retry mechanism
- ✅ Progress tracking
- ✅ Better scalability

---

## Security Best Practices

### 10. Input Sanitization

**Why:** Prevents NoSQL injection, XSS attacks, and data corruption.

**Implementation:**
```typescript
// Sanitization utilities
export function sanitizeString(input: string | undefined): string | undefined {
  if (!input) return undefined;
  return input.trim().replace(/[<>]/g, '');
}

export function sanitizeRegex(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function sanitizeObjectId(input: string): string | null {
  if (!Types.ObjectId.isValid(input)) return null;
  return input;
}

// Usage in queries
if (filters?.profileName) {
  const sanitized = sanitizeRegex(filters.profileName.trim());
  query.profileName = { $regex: sanitized, $options: "i" };
}
```

**Benefits:**
- ✅ Prevents injection attacks
- ✅ Data integrity
- ✅ Security compliance

---

### 11. CSRF Protection

**Why:** Prevents cross-site request forgery attacks.

**Implementation:**
```typescript
// CSRF Token Generation
async function generateCSRFToken(sessionId: string): Promise<string> {
  const token = crypto.randomBytes(32).toString('hex');
  await CSRFToken.create({
    sessionId,
    token,
    expiresAt: new Date(Date.now() + 3600000) // 1 hour
  });
  return token;
}

// CSRF Verification
async function verifyCSRFToken(sessionId: string, token: string): Promise<boolean> {
  const stored = await CSRFToken.findOne({
    sessionId,
    token,
    expiresAt: { $gt: new Date() }
  });
  return !!stored;
}

// Middleware
export async function csrfProtection(request: NextRequest) {
  if (!requiresCSRFProtection(request.method)) return null;
  
  const sessionId = await getSessionIdFromRequest(request);
  const token = extractCSRFToken(request);
  
  if (!token || !await verifyCSRFToken(sessionId, token)) {
    return NextResponse.json(
      { error: "Invalid or expired CSRF token" },
      { status: 403 }
    );
  }
  
  return null;
}
```

**Benefits:**
- ✅ Prevents CSRF attacks
- ✅ Secure state-changing operations
- ✅ Industry standard protection

---

### 12. Rate Limiting

**Why:** Prevents abuse, DoS attacks, and ensures fair resource usage.

**Implementation:**
```typescript
// Rate Limiting Middleware
class RateLimiter {
  private requests: Map<string, number[]> = new Map();
  
  check(identifier: string, limit: number, windowMs: number): boolean {
    const now = Date.now();
    const requests = this.requests.get(identifier) || [];
    
    // Remove old requests outside window
    const recent = requests.filter(time => now - time < windowMs);
    
    if (recent.length >= limit) {
      return false; // Rate limit exceeded
    }
    
    recent.push(now);
    this.requests.set(identifier, recent);
    return true;
  }
}

// Usage
export async function rateLimitMiddleware(request: NextRequest) {
  const ip = request.ip ?? '127.0.0.1';
  const limiter = new RateLimiter();
  
  if (!limiter.check(ip, 100, 60000)) { // 100 requests per minute
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429 }
    );
  }
}
```

**Benefits:**
- ✅ Prevents abuse
- ✅ Protects against DoS
- ✅ Fair resource allocation

---

### 13. Session Management

**Why:** Ensures secure authentication and prevents session hijacking.

**Implementation:**
```typescript
// Session Configuration
const sessionConfig = {
  strategy: "jwt",
  maxAge: 30 * 60, // 30 minutes
  updateAge: 5 * 60, // Refresh every 5 minutes
};

// Session Validation
export async function validateSession(session: Session): Promise<boolean> {
  if (!session?.expires) return false;
  
  const now = Date.now();
  const expiresAt = new Date(session.expires).getTime();
  
  // Check if session expired
  if (now > expiresAt) {
    return false;
  }
  
  // Check if needs refresh
  const refreshThreshold = expiresAt - (5 * 60 * 1000); // 5 minutes before expiry
  if (now > refreshThreshold) {
    await refreshSession(session);
  }
  
  return true;
}
```

**Benefits:**
- ✅ Secure authentication
- ✅ Automatic session refresh
- ✅ Prevents session hijacking

---

## Database Optimization

### 14. Database Indexing

**Why:** Dramatically improves query performance, especially on large datasets.

**Implementation:**
```typescript
// Compound Indexes
UserSchema.index({ email: 1, isActive: 1 });
IncentiveSchema.index({ userId: 1, status: 1, isActive: 1 });

// Text Indexes for Search
OpportunitySchema.index({ projectName: 'text', euid: 'text' });

// TTL Indexes for Auto-Cleanup
CSRFTokenSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });
```

**Benefits:**
- ✅ 10-100x faster queries
- ✅ Better scalability
- ✅ Reduced database load

---

### 15. Connection Pooling

**Why:** Efficiently manages database connections and prevents connection exhaustion.

**Implementation:**
```typescript
// MongoDB Connection with Pooling
let cached = global.mongoose;

if (!cached) {
  cached = global.mongoose = { conn: null, promise: null };
}

async function connectDB() {
  if (cached.conn) return cached.conn;
  
  if (!cached.promise) {
    const opts = {
      bufferCommands: false,
      maxPoolSize: 10,
      minPoolSize: 2,
      serverSelectionTimeoutMS: 5000,
      socketTimeoutMS: 45000,
    };
    
    cached.promise = mongoose.connect(MONGODB_URI, opts).then((mongoose) => {
      return mongoose;
    });
  }
  
  try {
    cached.conn = await cached.promise;
  } catch (e) {
    cached.promise = null;
    throw e;
  }
  
  return cached.conn;
}
```

**Benefits:**
- ✅ Efficient connection reuse
- ✅ Prevents connection exhaustion
- ✅ Better performance

---

## API Design

### 16. Standardized API Responses

**Why:** Consistent API responses improve developer experience and client-side handling.

**Implementation:**
```typescript
// Success Response
{
  success: true,
  data: T,
  message?: string
}

// Error Response
{
  success: false,
  error: {
    code: string,
    message: string,
    details?: unknown
  }
}

// Paginated Response
{
  success: true,
  data: T[],
  pagination: {
    page: number,
    pageSize: number,
    total: number,
    totalPages: number
  }
}
```

**Benefits:**
- ✅ Consistent API structure
- ✅ Easier client-side handling
- ✅ Better error handling

---

### 17. API Client Architecture

**Why:** Centralizes API calls, enables interceptors, and ensures consistency.

**Implementation:**
```typescript
// API Client with Interceptors
class ApiClient {
  private baseURL: string;
  private interceptors: Interceptor[] = [];
  
  async request<T>(url: string, options: RequestOptions): Promise<T> {
    // Request interceptors
    for (const interceptor of this.interceptors) {
      if (interceptor.request) {
        options = await interceptor.request(options);
      }
    }
    
    const response = await fetch(`${this.baseURL}${url}`, options);
    
    // Response interceptors
    for (const interceptor of this.interceptors) {
      if (interceptor.response) {
        await interceptor.response(response);
      }
    }
    
    return response.json();
  }
  
  addInterceptor(interceptor: Interceptor) {
    this.interceptors.push(interceptor);
  }
}

// CSRF Token Interceptor
apiClient.addInterceptor({
  request: async (options) => {
    const token = await getCSRFToken();
    options.headers = {
      ...options.headers,
      'X-CSRF-Token': token
    };
    return options;
  }
});

// Caching Interceptor
apiClient.addInterceptor({
  response: async (response) => {
    if (response.ok) {
      const cacheKey = response.url;
      cache.set(cacheKey, await response.clone().json());
    }
  }
});
```

**Benefits:**
- ✅ No direct fetch calls
- ✅ Centralized configuration
- ✅ Easy to add cross-cutting concerns
- ✅ Consistent error handling

---

## Error Handling & Logging

### 18. Structured Logging

**Why:** Enables better debugging, monitoring, and observability.

**Implementation:**
```typescript
// Structured Logger
class Logger {
  log(level: LogLevel, message: string, context: Record<string, unknown> = {}) {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...context
    };
    
    console.log(JSON.stringify(entry));
    
    // Send to monitoring service in production
    if (process.env.NODE_ENV === 'production') {
      monitoringService.log(entry);
    }
  }
  
  error(message: string, error: unknown, context: Record<string, unknown> = {}) {
    this.log('error', message, {
      ...context,
      error: error instanceof Error ? {
        message: error.message,
        stack: error.stack
      } : error
    });
  }
}

// Usage
logger.error("Failed to create user", error, {
  userId: user.id,
  operation: "createUser"
});
```

**Benefits:**
- ✅ Better debugging
- ✅ Production monitoring
- ✅ Error tracking
- ✅ Performance insights

---

### 19. Error Sanitization

**Why:** Prevents information leakage in production while maintaining useful errors in development.

**Implementation:**
```typescript
export function sanitizeErrorMessage(
  error: unknown,
  defaultMessage: string,
  operation: string
): { message: string; statusCode: number } {
  const rawErrorMessage = error instanceof Error ? error.message : defaultMessage;
  
  // In production, sanitize error messages
  const errorMessage = process.env.NODE_ENV === "production"
    ? "An error occurred while processing your request"
    : rawErrorMessage;
  
  let statusCode = 500;
  
  // Handle specific error types
  if (/already exists/i.test(rawErrorMessage)) {
    statusCode = 409;
    return {
      message: process.env.NODE_ENV === "production"
        ? "Resource already exists"
        : rawErrorMessage,
      statusCode
    };
  }
  
  return { message: errorMessage, statusCode };
}
```

**Benefits:**
- ✅ Security (no information leakage)
- ✅ Better user experience
- ✅ Detailed errors in development

---

## Testing Strategy

### 20. Integration Tests

**Why:** Ensures API routes work correctly end-to-end.

**Implementation:**
```typescript
// Test Utilities
export async function createTestRequest(
  method: string,
  path: string,
  body?: unknown
): Promise<NextRequest> {
  const url = `http://localhost:3000${path}`;
  return new NextRequest(url, {
    method,
    body: body ? JSON.stringify(body) : undefined,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

// Integration Test
describe('POST /api/users', () => {
  it('should create a user', async () => {
    const request = await createTestRequest('POST', '/api/users', {
      name: 'Test User',
      email: 'test@example.com'
    });
    
    const response = await POST(request);
    const data = await response.json();
    
    expect(response.status).toBe(200);
    expect(data.success).toBe(true);
    expect(data.data.email).toBe('test@example.com');
  });
});
```

**Benefits:**
- ✅ End-to-end validation
- ✅ Catches integration issues
- ✅ Confidence in deployments

---

## Scalability Patterns

### 21. Stateless Design

**Why:** Enables horizontal scaling and load balancing.

**Implementation:**
- ✅ Store state in database, not memory
- ✅ Use external session storage (database, Redis)
- ✅ Avoid server-side state
- ✅ Use connection pooling

**Benefits:**
- ✅ Horizontal scaling
- ✅ Load balancing
- ✅ High availability

---

### 22. Background Processing

**Why:** Handles long-running tasks without blocking API requests.

**Implementation:**
- ✅ Job queue for async processing
- ✅ Background workers
- ✅ Progress tracking
- ✅ Retry mechanisms

**Benefits:**
- ✅ Non-blocking APIs
- ✅ Better user experience
- ✅ Scalable processing

---

## Modern JavaScript/TypeScript Practices

### 23. Type Safety

**Why:** Prevents runtime errors, improves developer experience, and enables better tooling.

**Implementation:**
```typescript
// Type Guards
export function isAuthError(authResult: unknown): authResult is NextResponse {
  return authResult instanceof NextResponse;
}

// Generic Functions
export function normalizeToArray<T>(
  result: T[] | { data: T[] } | null | undefined
): T[] {
  // Implementation
}

// Strict TypeScript Configuration
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true
  }
}
```

**Benefits:**
- ✅ Catch errors at compile time
- ✅ Better IDE support
- ✅ Self-documenting code

---

### 24. ES6+ Features

**Why:** Modern JavaScript features improve code quality and maintainability.

**Best Practices:**
- ✅ Use `async/await` instead of callbacks
- ✅ Use `const` and `let` instead of `var`
- ✅ Use arrow functions for callbacks
- ✅ Use template literals for strings
- ✅ Use destructuring for objects/arrays
- ✅ Use optional chaining (`?.`) and nullish coalescing (`??`)
- ✅ Use spread operator for arrays/objects

**Benefits:**
- ✅ Cleaner code
- ✅ Better performance
- ✅ Modern best practices

---

## React 19 Built-in Hooks

### 25. useActionState (formerly useFormState)

**Why:** Manages form state and actions with built-in pending state, reducing boilerplate.

**Implementation:**
```typescript
// React 19: useActionState
import { useActionState } from "react";

async function createUser(prevState: unknown, formData: FormData) {
  const name = formData.get("name") as string;
  
  try {
    await userService.create({ name });
    return { success: true, message: "User created" };
  } catch (error) {
    return { success: false, error: "Failed to create user" };
  }
}

function UserForm() {
  const [state, formAction, isPending] = useActionState(createUser, null);

  return (
    <form action={formAction}>
      <input name="name" disabled={isPending} />
      <button disabled={isPending}>
        {isPending ? "Creating..." : "Create User"}
      </button>
      {state?.error && <p>{state.error}</p>}
    </form>
  );
}
```

**Benefits:**
- ✅ Built-in pending state
- ✅ Automatic form state management
- ✅ Server actions integration
- ✅ Less boilerplate

---

### 26. useOptimistic

**Why:** Enables optimistic UI updates, improving perceived performance.

**Implementation:**
```typescript
import { useOptimistic, useTransition } from "react";

function TodoList({ todos }: { todos: Todo[] }) {
  const [isPending, startTransition] = useTransition();
  const [optimisticTodos, addOptimisticTodo] = useOptimistic(
    todos,
    (state, newTodo: Todo) => [...state, newTodo]
  );

  async function addTodo(formData: FormData) {
    const text = formData.get("text") as string;
    const newTodo = { id: Date.now(), text, completed: false };

    // Optimistically update UI
    addOptimisticTodo(newTodo);

    // Actually create todo
    startTransition(async () => {
      await todoService.create(newTodo);
    });
  }

  return (
    <div>
      {optimisticTodos.map((todo) => (
        <div key={todo.id}>{todo.text}</div>
      ))}
      <form action={addTodo}>
        <input name="text" />
        <button disabled={isPending}>Add</button>
      </form>
    </div>
  );
}
```

**Benefits:**
- ✅ Instant UI feedback
- ✅ Better user experience
- ✅ Automatic rollback on error
- ✅ Built-in state management

---

### 27. useFormStatus

**Why:** Allows child components to access form submission status without prop drilling.

**Implementation:**
```typescript
import { useFormStatus } from "react-dom";

function SubmitButton() {
  const { pending, data, method, action } = useFormStatus();

  return (
    <button type="submit" disabled={pending}>
      {pending ? "Submitting..." : "Submit"}
    </button>
  );
}

function UserForm() {
  return (
    <form action={createUser}>
      <input name="name" />
      <SubmitButton /> {/* No props needed! */}
    </form>
  );
}
```

**Benefits:**
- ✅ No prop drilling
- ✅ Automatic status tracking
- ✅ Clean component structure
- ✅ Works with server actions

---

### 28. useTransition

**Why:** Marks state updates as non-urgent, keeping UI responsive during heavy operations.

**Implementation:**
```typescript
import { useTransition, useState } from "react";

function SearchResults({ query }: { query: string }) {
  const [isPending, startTransition] = useTransition();
  const [results, setResults] = useState([]);

  useEffect(() => {
    startTransition(async () => {
      const data = await searchService.search(query);
      setResults(data);
    });
  }, [query]);

  return (
    <div>
      {isPending && <Spinner />}
      {results.map((result) => (
        <div key={result.id}>{result.title}</div>
      ))}
    </div>
  );
}
```

**Benefits:**
- ✅ Keeps UI responsive
- ✅ Prioritizes urgent updates
- ✅ Better user experience
- ✅ Built-in loading state

---

### 29. useDeferredValue

**Why:** Defers updating a value until after urgent updates, improving performance.

**Implementation:**
```typescript
import { useDeferredValue, useMemo } from "react";

function ExpensiveList({ items }: { items: Item[] }) {
  const deferredItems = useDeferredValue(items);

  const filtered = useMemo(() => {
    return deferredItems.filter(item => item.active);
  }, [deferredItems]);

  return (
    <div>
      {filtered.map(item => (
        <div key={item.id}>{item.name}</div>
      ))}
    </div>
  );
}
```

**Benefits:**
- ✅ Defers expensive computations
- ✅ Prioritizes urgent updates
- ✅ Better performance
- ✅ Automatic optimization

---

### 30. useSyncExternalStore

**Why:** Subscribes to external stores (like Zustand, Redux) with proper synchronization.

**Implementation:**
```typescript
import { useSyncExternalStore } from "react";

function useStore<T>(store: Store<T>) {
  return useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getServerSnapshot // For SSR
  );
}

// Usage with Zustand
const users = useStore(useUsersStore, (state) => state.users);
```

**Benefits:**
- ✅ Proper external store integration
- ✅ SSR support
- ✅ Automatic synchronization
- ✅ Prevents tearing

---

## Zustand State Management Issues

### 31. Overusing Global State

**Why:** Storing too much state globally leads to unnecessary complexity and re-renders.

**Problem:**
```typescript
// ❌ Bad: Everything in global state
const useAppStore = create((set) => ({
  users: [],
  roles: [],
  opportunities: [],
  currentUser: null,
  theme: "light",
  sidebarOpen: true,
  modalOpen: false,
  formData: {},
  // ... 50 more fields
}));
```

**Solution:**
```typescript
// ✅ Good: Split into focused stores
const useUsersStore = create((set) => ({
  users: [],
  loading: false,
}));

const useUIStore = create((set) => ({
  theme: "light",
  sidebarOpen: true,
}));

// ✅ Good: Use local state for component-specific data
function UserForm() {
  const [formData, setFormData] = useState({}); // Local state
  const { createUser } = useUsersStore(); // Only what's needed
}
```

**Best Practices:**
- ✅ Keep global state minimal (shared across multiple components)
- ✅ Use local state for component-specific data
- ✅ Split stores by domain (users, UI, auth, etc.)
- ✅ Only store what needs to be shared

---

### 32. Not Using Selectors

**Why:** Without selectors, components re-render on any store change, even if they don't use that data.

**Problem:**
```typescript
// ❌ Bad: Component re-renders on any store change
function UserList() {
  const store = useUsersStore(); // Re-renders when ANY field changes
  return <div>{store.users.map(...)}</div>;
}

// Even if only `loading` changes, component re-renders
```

**Solution:**
```typescript
// ✅ Good: Use selectors to subscribe to specific fields
function UserList() {
  const users = useUsersStore((state) => state.users); // Only re-renders when users change
  return <div>{users.map(...)}</div>;
}

// ✅ Good: Select multiple fields with equality check
function UserCard({ userId }: { userId: string }) {
  const user = useUsersStore(
    (state) => state.users.find((u) => u.id === userId),
    (a, b) => a?.name === b?.name && a?.email === b?.email // Custom equality
  );
  return <div>{user?.name}</div>;
}
```

**Best Practices:**
- ✅ Always use selectors for store access
- ✅ Use shallow equality for objects/arrays
- ✅ Create custom equality functions when needed
- ✅ Use `useShallow` for multiple field selection

---

### 33. Direct State Mutation

**Why:** Mutating state directly breaks React's reactivity and can cause bugs.

**Problem:**
```typescript
// ❌ Bad: Direct mutation (even with Immer, this is wrong)
const useUsersStore = create((set) => ({
  users: [],
  addUser: (user) => {
    const state = useUsersStore.getState();
    state.users.push(user); // Direct mutation!
    set(state); // This won't trigger re-renders properly
  },
}));
```

**Solution:**
```typescript
// ✅ Good: Use set function (with Immer)
const useUsersStore = create(
  immer((set) => ({
    users: [],
    addUser: (user) => {
      set((state) => {
        state.users.push(user); // Immer handles immutability
      });
    },
  }))
);

// ✅ Good: Without Immer, return new state
const useUsersStore = create((set) => ({
  users: [],
  addUser: (user) => {
    set((state) => ({
      ...state,
      users: [...state.users, user], // New array reference
    }));
  },
}));
```

**Best Practices:**
- ✅ Always use `set` function to update state
- ✅ Use Immer middleware for complex updates
- ✅ Return new object/array references
- ✅ Never mutate state directly

---

### 34. Overcomplicating the Store

**Why:** Complex stores with nested logic are hard to maintain and test.

**Problem:**
```typescript
// ❌ Bad: Store does too much
const useUsersStore = create((set, get) => ({
  users: [],
  async fetchUsers() {
    // API call
    // Error handling
    // Caching logic
    // Permission checking
    // Notification
    // Analytics tracking
    // ... 100 lines of code
  },
}));
```

**Solution:**
```typescript
// ✅ Good: Keep store simple, move logic to services
const useUsersStore = create((set) => ({
  users: [],
  loading: false,
  error: null,
  setUsers: (users) => set({ users }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));

// Logic in service
class UserService {
  async fetchUsers() {
    useUsersStore.getState().setLoading(true);
    try {
      const users = await api.getUsers();
      useUsersStore.getState().setUsers(users);
    } catch (error) {
      useUsersStore.getState().setError(error.message);
    } finally {
      useUsersStore.getState().setLoading(false);
    }
  }
}
```

**Best Practices:**
- ✅ Keep stores focused on state management
- ✅ Move business logic to services
- ✅ Use actions for simple state updates
- ✅ Keep stores under 200 lines

---

### 35. Not Handling Async Actions Properly

**Why:** Async actions in Zustand can cause race conditions and stale state.

**Problem:**
```typescript
// ❌ Bad: Race conditions
const useUsersStore = create((set, get) => ({
  users: [],
  async fetchUsers() {
    const users = await api.getUsers();
    set({ users }); // Might be stale if called multiple times
  },
}));

// Multiple calls can cause race conditions
fetchUsers(); // Call 1
fetchUsers(); // Call 2 (might finish first)
```

**Solution:**
```typescript
// ✅ Good: Prevent duplicate calls
const useUsersStore = create((set, get) => ({
  users: [],
  loading: false,
  async fetchUsers() {
    if (get().loading) return; // Prevent duplicate calls
    
    set({ loading: true });
    try {
      const users = await api.getUsers();
      set({ users, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },
}));

// ✅ Good: Use AbortController for cancellation
const useUsersStore = create((set, get) => {
  let abortController: AbortController | null = null;
  
  return {
    users: [],
    async fetchUsers() {
      // Cancel previous request
      abortController?.abort();
      abortController = new AbortController();
      
      set({ loading: true });
      try {
        const users = await api.getUsers({ signal: abortController.signal });
        set({ users, loading: false });
      } catch (error) {
        if (error.name !== "AbortError") {
          set({ error: error.message, loading: false });
        }
      }
    },
  };
});
```

**Best Practices:**
- ✅ Check loading state before async actions
- ✅ Use AbortController for cancellation
- ✅ Handle errors properly
- ✅ Clean up on unmount

---

### 36. Missing TypeScript Types

**Why:** Without proper types, Zustand stores lose type safety and IDE support.

**Problem:**
```typescript
// ❌ Bad: No types
const useUsersStore = create((set) => ({
  users: [],
  addUser: (user) => {
    // No type checking!
  },
}));
```

**Solution:**
```typescript
// ✅ Good: Proper TypeScript types
interface UsersState {
  users: User[];
  loading: boolean;
  error: string | null;
  addUser: (user: User) => void;
  fetchUsers: () => Promise<void>;
}

const useUsersStore = create<UsersState>()((set) => ({
  users: [],
  loading: false,
  error: null,
  addUser: (user) => {
    set((state) => ({ ...state, users: [...state.users, user] }));
  },
  fetchUsers: async () => {
    // Type-safe implementation
  },
}));
```

**Best Practices:**
- ✅ Always define TypeScript interfaces
- ✅ Use `create<T>()()` syntax for type inference
- ✅ Type actions and state separately
- ✅ Export types for reuse

---

## XSS Protection

### 37. Client-Side XSS Protection

**Why:** Prevents malicious scripts from executing in the browser.

**Implementation:**
```typescript
// HTML Escaping
export function escapeHTML(str: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return str.replace(/[&<>"']/g, (m) => map[m]);
}

// React: Use dangerouslySetInnerHTML sparingly
// ❌ Bad: Direct HTML injection
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// ✅ Good: Escape or sanitize
<div>{escapeHTML(userInput)}</div>

// Or use a sanitization library
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userInput) }} />
```

---

### 38. Server-Side XSS Protection

**Why:** Prevents XSS in API responses, exports, and server-rendered content.

**Implementation:**
```typescript
// CSV Export Protection
export function escapeCSV(value: unknown): string {
  if (value === null || value === undefined) return "";
  const str = String(value);
  
  // Escape special characters
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  
  // Prevent formula injection
  const dangerousChars = ["=", "+", "-", "@", "\t"];
  if (dangerousChars.some((char) => str.startsWith(char))) {
    return `'${str}`; // Prefix with single quote
  }
  
  return str;
}

// JSON Response Sanitization
export function sanitizeForJSON(data: unknown): unknown {
  if (typeof data === "string") {
    return escapeHTML(data);
  }
  if (Array.isArray(data)) {
    return data.map(sanitizeForJSON);
  }
  if (data && typeof data === "object") {
    const sanitized: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(data)) {
      sanitized[escapeHTML(key)] = sanitizeForJSON(value);
    }
    return sanitized;
  }
  return data;
}
```

**Content Security Policy (CSP):**
```typescript
// next.config.ts
const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: `
      default-src 'self';
      script-src 'self' 'unsafe-inline' 'unsafe-eval';
      style-src 'self' 'unsafe-inline';
      img-src 'self' data: https:;
      font-src 'self' data:;
    `.replace(/\s{2,}/g, " ").trim(),
  },
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "X-XSS-Protection",
    value: "1; mode=block",
  },
];
```

**Benefits:**
- ✅ Prevents script injection
- ✅ Protects user data
- ✅ Secure exports
- ✅ Browser-level protection

---

## Preventing Multiple API Calls

### 39. Request Deduplication

**Why:** Prevents duplicate API calls when multiple components request the same data.

**Implementation:**
```typescript
// Request Cache with Deduplication
class RequestDeduplicator {
  private pendingRequests: Map<string, Promise<unknown>> = new Map();

  async request<T>(
    key: string,
    fetcher: () => Promise<T>
  ): Promise<T> {
    // If request is already pending, return the same promise
    if (this.pendingRequests.has(key)) {
      return this.pendingRequests.get(key) as Promise<T>;
    }

    // Create new request
    const promise = fetcher().finally(() => {
      this.pendingRequests.delete(key);
    });

    this.pendingRequests.set(key, promise);
    return promise;
  }
}

// Usage in hook
const deduplicator = new RequestDeduplicator();

export function useUsers() {
  const [users, setUsers] = useState([]);
  const fetchingRef = useRef(false);

  useEffect(() => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;

    deduplicator
      .request("users", () => userService.getAll())
      .then(setUsers)
      .finally(() => {
        fetchingRef.current = false;
      });
  }, []);
}
```

---

### 40. HTTP Caching with Interceptors

**Why:** Automatically caches responses and prevents duplicate requests.

**Implementation:**
```typescript
// Cache Interceptor
class CacheInterceptor {
  private cache: Map<string, CacheEntry> = new Map();

  async intercept(request: Request): Promise<Response> {
    const cacheKey = this.getCacheKey(request);

    // Check cache
    const cached = this.cache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return new Response(JSON.stringify(cached.data), {
        headers: { "X-Cache": "HIT" },
      });
    }

    // Make request
    const response = await fetch(request);
    const data = await response.json();

    // Cache response
    if (response.ok) {
      this.cache.set(cacheKey, {
        data,
        expiresAt: Date.now() + 300000, // 5 minutes
      });
    }

    return response;
  }

  invalidate(pattern: string) {
    for (const key of this.cache.keys()) {
      if (key.includes(pattern)) {
        this.cache.delete(key);
      }
    }
  }
}
```

**Benefits:**
- ✅ Automatic deduplication
- ✅ Reduced network traffic
- ✅ Faster responses
- ✅ Better user experience

---

## Duplicate Code Patterns

### 41. Common Duplicate Patterns to Avoid

**Pattern 1: Repeated Error Handling**
```typescript
// ❌ Bad: Duplicate error handling
try {
  const users = await fetchUsers();
} catch (error) {
  console.error("Error fetching users:", error);
  setError("Failed to fetch users");
}

try {
  const roles = await fetchRoles();
} catch (error) {
  console.error("Error fetching roles:", error);
  setError("Failed to fetch roles");
}

// ✅ Good: Extract to utility
async function handleAsync<T>(
  promise: Promise<T>,
  errorMessage: string
): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    console.error(errorMessage, error);
    return null;
  }
}

const users = await handleAsync(fetchUsers(), "Error fetching users");
const roles = await handleAsync(fetchRoles(), "Error fetching roles");
```

**Pattern 2: Repeated Validation**
```typescript
// ❌ Bad: Duplicate validation
if (!email || !email.includes("@")) {
  return { error: "Invalid email" };
}
if (!password || password.length < 8) {
  return { error: "Password too short" };
}

// ✅ Good: Validation utility
const validators = {
  email: (value: string) => {
    if (!value || !value.includes("@")) {
      return "Invalid email";
    }
  },
  password: (value: string) => {
    if (!value || value.length < 8) {
      return "Password too short";
    }
  },
};

function validate(data: Record<string, string>) {
  for (const [key, value] of Object.entries(data)) {
    const error = validators[key]?.(value);
    if (error) return { error };
  }
  return { valid: true };
}
```

**Pattern 3: Repeated Loading States**
```typescript
// ❌ Bad: Duplicate loading logic
const [usersLoading, setUsersLoading] = useState(false);
const [rolesLoading, setRolesLoading] = useState(false);

// ✅ Good: Generic loading hook
function useAsyncData<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetcher()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
```

**Benefits:**
- ✅ 90%+ reduction in duplicate code
- ✅ Consistent behavior
- ✅ Easier maintenance
- ✅ Better testing

---

## SOLID Principles

**OOP Concepts (practical guidance for this codebase)**
- Encapsulation: keep state/behavior inside services/repositories/strategies; expose minimal public surface.
- Abstraction + DIP: depend on interfaces and inject implementations (e.g., strategies for auth, search, pagination, rate limit store).
- Polymorphism: prefer Strategy Pattern over conditionals; swap behaviors via interfaces.
- Composition over inheritance: use small composable classes; inherit only where it preserves substitutability (e.g., BaseRepository).
- SRP + ISP: one reason to change; keep interfaces focused.
- Testability: inject dependencies; avoid hard-coded globals.

### 42. Single Responsibility Principle (SRP)

**Why:** Each class/function should have one reason to change.

**Implementation:**
```typescript
// ❌ Bad: Multiple responsibilities
class UserManager {
  async createUser(data: UserData) {
    // 1. Validation
    if (!data.email) throw new Error("Email required");
    
    // 2. Business logic
    const hashedPassword = await hash(data.password);
    
    // 3. Data access
    const user = await User.create({ ...data, password: hashedPassword });
    
    // 4. Notification
    await emailService.sendWelcome(user);
    
    // 5. Logging
    await logger.log("User created", user);
    
    return user;
  }
}

// ✅ Good: Single responsibility
class UserValidator {
  validate(data: UserData): ValidationResult {
    if (!data.email) return { valid: false, error: "Email required" };
    return { valid: true };
  }
}

class UserService {
  async createUser(data: UserData): Promise<User> {
    const hashedPassword = await hash(data.password);
    return User.create({ ...data, password: hashedPassword });
  }
}

// Usage with events
const user = await userService.createUser(validatedData);
eventEmitter.emit(USER_EVENTS.CREATED, { userId: user.id });
```

---

### 43. Open/Closed Principle (OCP)

**Why:** Software should be open for extension but closed for modification.

**Implementation:**
```typescript
// ✅ Good: Extensible without modification
abstract class PaymentProcessor {
  abstract process(amount: number): Promise<PaymentResult>;
}

class CreditCardProcessor extends PaymentProcessor {
  async process(amount: number): Promise<PaymentResult> {
    // Credit card logic
  }
}

class PayPalProcessor extends PaymentProcessor {
  async process(amount: number): Promise<PaymentResult> {
    // PayPal logic
  }
}

// Add new payment method without modifying existing code
class StripeProcessor extends PaymentProcessor {
  async process(amount: number): Promise<PaymentResult> {
    // Stripe logic
  }
}
```

---

### 44. Liskov Substitution Principle (LSP)

**Why:** Subtypes must be substitutable for their base types.

**Implementation:**
```typescript
// ✅ Good: All repositories are substitutable
interface IRepository<T> {
  findById(id: string): Promise<T | null>;
  findAll(): Promise<T[]>;
  create(data: Partial<T>): Promise<T>;
}

class UserRepository implements IRepository<User> {
  // Implementation
}

class RoleRepository implements IRepository<Role> {
  // Implementation
}

// Can use any repository interchangeably
function processEntity<T>(repository: IRepository<T>, id: string) {
  return repository.findById(id);
}
```

---

### 45. Interface Segregation Principle (ISP)

**Why:** Clients shouldn't depend on interfaces they don't use.

**Implementation:**
```typescript
// ❌ Bad: Fat interface
interface IUserService {
  createUser(): Promise<User>;
  updateUser(): Promise<User>;
  deleteUser(): Promise<void>;
  sendEmail(): Promise<void>; // Not all clients need this
  generateReport(): Promise<Report>; // Not all clients need this
}

// ✅ Good: Segregated interfaces
interface IUserCRUD {
  createUser(): Promise<User>;
  updateUser(): Promise<User>;
  deleteUser(): Promise<void>;
}

interface IUserEmail {
  sendEmail(): Promise<void>;
}

interface IUserReporting {
  generateReport(): Promise<Report>;
}

// Clients only depend on what they need
class UserController implements IUserCRUD {
  // Only CRUD methods
}
```

---

### 46. Dependency Inversion Principle (DIP)

**Why:** High-level modules shouldn't depend on low-level modules. Both should depend on abstractions.

**Implementation:**
```typescript
// ❌ Bad: Direct dependency
class UserService {
  private db = new MongoDB(); // Depends on concrete implementation
}

// ✅ Good: Depends on abstraction
interface IDatabase {
  findOne(query: Record<string, unknown>): Promise<unknown>;
  create(data: unknown): Promise<unknown>;
}

class UserService {
  constructor(private db: IDatabase) {} // Depends on interface
}

// Can swap implementations
const userService = new UserService(new MongoDB());
const userService2 = new UserService(new PostgreSQL());
```

---

## Design Patterns

### 47. Factory Pattern

**Why:** Creates objects without specifying exact classes.

**Implementation:**
```typescript
// Service Factory
class ServiceFactory {
  static createUserService(): UserService {
    return new UserService(new UserRepository());
  }

  static createRoleService(): RoleService {
    return new RoleService(new RoleRepository());
  }

  static createService<T>(type: ServiceType): T {
    switch (type) {
      case ServiceType.USER:
        return this.createUserService() as T;
      case ServiceType.ROLE:
        return this.createRoleService() as T;
      default:
        throw new Error(`Unknown service type: ${type}`);
    }
  }
}
```

---

### 48. Strategy Pattern

**Why:** Defines a family of algorithms and makes them interchangeable.

**Implementation:**
```typescript
// CSRF Token Storage Strategy
interface ICSRFTokenStorage {
  set(sessionId: string, token: string, expiresAt: Date): Promise<void>;
  get(sessionId: string): Promise<ICSRFToken | null>;
  delete(sessionId: string): Promise<void>;
}

class DatabaseCSRFTokenStorage implements ICSRFTokenStorage {
  // Database implementation
}

class MemoryCSRFTokenStorage implements ICSRFTokenStorage {
  // Memory implementation
}

// Composite strategy (database first, fallback to memory)
class CompositeCSRFTokenStorage implements ICSRFTokenStorage {
  constructor(
    private primary: ICSRFTokenStorage,
    private fallback: ICSRFTokenStorage
  ) {}

  async set(...args: Parameters<ICSRFTokenStorage["set"]>) {
    try {
      await this.primary.set(...args);
    } catch {
      await this.fallback.set(...args);
    }
  }
}
```

---

### 48.a. Authentication & Authorization Strategies

**Why:** Swap auth mechanisms without touching business logic; enforce policies consistently.

**Authentication (`IAuthStrategy`):**
- JWTAuthStrategy (Authorization: Bearer)
- SessionAuthStrategy (secure SameSite cookies)
- ApiKeyAuthStrategy (header `x-api-key`)

**Authorization (`IAuthorizationStrategy`):**
- RoleBasedAuthorizationStrategy (role → actions)
- OwnershipAuthorizationStrategy (resource.ownerId === user.id)
- AttributeBasedAuthorizationStrategy (custom predicate)

**Apply:** API middleware combines auth + authz before handlers.

---

### 48.b. Rate Limit Store Strategy

**Why:** Support single-instance (memory) and distributed (Redis) rate limits.
- Interface: `IRateLimitStore` + `StoreBackedRateLimitStrategy`
- Stores: MemoryRateLimitStore, RedisRateLimitStore (stub; wire real Redis)
- Configure in rate-limit middleware; use SameSite cookies for session IDs.

---

### 48.c. Session Storage Strategy

**Why:** Pluggable session backends.
- Interfaces: `ISessionStorage`, `ISessionData`
- Stores: DatabaseSessionStorage, MemorySessionStorage, RedisSessionStorage (stub)
- Use secure, httpOnly, SameSite=Strict cookies for sessionId.

---

### 48.d. Retry & Backoff Strategies

**Why:** Resilience for external calls.
- Interface: `IRetryStrategy`
- Strategies: ExponentialBackoffStrategy (with jitter), FixedRetryStrategy
- Service: `RetryService` (wrapping API calls)

---

### 48.e. Circuit Breaker Strategies

**Why:** Prevent cascading failures.
- Interface: `ICircuitBreaker`
- Strategies: SimpleCircuitBreaker (default), NoopCircuitBreaker
- Service: `CircuitBreakerService` (wraps retries/external calls)
- Default thresholds: 5 failures, 30s reset window (tune per endpoint).

---

### 48.f. Import/Export Strategies

**Why:** Support multiple formats without branching.
- Export: CSV, JSON, XLSX (stub), PDF (stub) via `IDataExportStrategy`
- Import: `IImportStrategy` (CSV/XLSX/JSON parsers can be plugged)

---

### 48.g. Validation Strictness Strategy

**Why:** Different tolerance for imports vs user-facing forms.
- Interface: `IValidationStrategy`
- Strategies: StrictValidationStrategy (default), LenientValidationStrategy (converts errors to warnings)
- Validators accept strategy injection; services stay unchanged.

---

### 48.h. Client Data Access (React Query) – OOP Alignment

**Why:** Keep hooks thin and testable; encapsulate data access in services.
- Hooks: stay as thin facades that call service methods (or API client) and expose query/mutation results.
- Services: class-based (already in `lib/services/*`) to encapsulate business logic and data access.
- Adapters: use strategy/adapter patterns for backend differences (e.g., API shapes, pagination).

**Guideline:** Prefer “service → hook” flow: service methods return promises; hooks wrap them with React Query for caching/retries.

---

### 49. Observer Pattern

**Why:** Defines one-to-many dependency between objects.

**Implementation:**
```typescript
// Event Emitter (Observer Pattern)
class EventEmitter {
  private listeners: Map<string, Function[]> = new Map();

  on(event: string, handler: Function) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event)!.push(handler);
  }

  off(event: string, handler: Function) {
    const handlers = this.listeners.get(event) || [];
    const index = handlers.indexOf(handler);
    if (index > -1) {
      handlers.splice(index, 1);
    }
  }

  emit(event: string, data: unknown) {
    const handlers = this.listeners.get(event) || [];
    handlers.forEach((handler) => {
      try {
        handler(data);
      } catch (error) {
        console.error(`Error in event handler for ${event}:`, error);
      }
    });
  }
}
```

---

### 50. Singleton Pattern

**Why:** Ensures a class has only one instance.

**Implementation:**
```typescript
// Singleton Service
class JobQueueService {
  private static instance: JobQueueService;

  private constructor() {
    // Private constructor
  }

  static getInstance(): JobQueueService {
    if (!JobQueueService.instance) {
      JobQueueService.instance = new JobQueueService();
    }
    return JobQueueService.instance;
  }
}

// Usage
const jobQueue = JobQueueService.getInstance();
```

---

### 51. Adapter Pattern

**Why:** Allows incompatible interfaces to work together.

**Implementation:**
```typescript
// Adapter for different API formats
interface IApiAdapter {
  fetchUsers(): Promise<User[]>;
}

class RESTApiAdapter implements IApiAdapter {
  async fetchUsers(): Promise<User[]> {
    const response = await fetch("/api/users");
    return response.json();
  }
}

class GraphQLApiAdapter implements IApiAdapter {
  async fetchUsers(): Promise<User[]> {
    const response = await fetch("/graphql", {
      method: "POST",
      body: JSON.stringify({ query: "{ users { id name } }" }),
    });
    const { data } = await response.json();
    return data.users;
  }
}

// Service uses adapter interface
class UserService {
  constructor(private adapter: IApiAdapter) {}

  async getUsers(): Promise<User[]> {
    return this.adapter.fetchUsers();
  }
}
```

---

### 52. Decorator Pattern

**Why:** Adds behavior to objects dynamically.

**Implementation:**
```typescript
// Caching Decorator
function withCache<T extends (...args: unknown[]) => Promise<unknown>>(
  fn: T,
  ttl: number = 300000
): T {
  const cache = new Map<string, { data: unknown; expiresAt: number }>();

  return (async (...args: Parameters<T>) => {
    const key = JSON.stringify(args);
    const cached = cache.get(key);

    if (cached && cached.expiresAt > Date.now()) {
      return cached.data;
    }

    const result = await fn(...args);
    cache.set(key, {
      data: result,
      expiresAt: Date.now() + ttl,
    });

    return result;
  }) as T;
}

// Usage
const cachedFetchUsers = withCache(fetchUsers, 300000);
```

---

### 53. Chain of Responsibility Pattern

**Why:** Passes requests along a chain of handlers.

**Implementation:**
```typescript
// Middleware Chain
interface Middleware {
  handle(request: Request, next: () => Promise<Response>): Promise<Response>;
}

class AuthMiddleware implements Middleware {
  async handle(request: Request, next: () => Promise<Response>) {
    if (!request.headers.get("Authorization")) {
      return new Response("Unauthorized", { status: 401 });
    }
    return next();
  }
}

class CSRFMiddleware implements Middleware {
  async handle(request: Request, next: () => Promise<Response>) {
    if (!this.verifyCSRF(request)) {
      return new Response("Invalid CSRF token", { status: 403 });
    }
    return next();
  }
}

// Chain execution
async function executeChain(
  request: Request,
  middlewares: Middleware[],
  handler: () => Promise<Response>
): Promise<Response> {
  let index = 0;

  const next = async (): Promise<Response> => {
    if (index >= middlewares.length) {
      return handler();
    }
    const middleware = middlewares[index++];
    return middleware.handle(request, next);
  };

  return next();
}
```

---

## Implementation Checklist & Summary

### Critical (Must Have)
- [ ] Event-Driven Architecture
- [ ] Repository Pattern
- [ ] Utility Functions Library
- [ ] Input Sanitization
- [ ] CSRF Protection
- [ ] Rate Limiting
- [ ] Database Indexing
- [ ] Pagination
- [ ] Error Sanitization
- [ ] Structured Logging

### High Priority (Should Have)
- [ ] Job Queue System
- [ ] Batch API
- [ ] Caching Strategy
- [ ] Database Aggregation Pipelines
- [ ] Session Management
- [ ] API Client Architecture
- [ ] Standardized API Responses
- [ ] Connection Pooling

### Medium Priority (Nice to Have)
- [ ] Integration Tests
- [ ] Type Safety (strict TypeScript)
- [ ] Modern ES6+ Features
- [ ] Stateless Design
- [ ] Background Processing
- [ ] Custom React Hooks
- [ ] Request Deduplication
- [ ] XSS Protection (Client & Server)
- [ ] SOLID Principles
- [ ] Design Patterns (Factory, Strategy, Observer, etc.)

---

## React 19 & Next.js App Router Best Practices

### 54. useTransition for Non-Urgent Updates

**Why:** Keeps UI responsive during heavy operations by marking state updates as non-urgent.

**Implementation:**
```typescript
import { useTransition } from "react";

function SearchPage() {
  const [isPending, startTransition] = useTransition();
  const [search, setSearch] = useState("");

  return (
    <input
      value={search}
      onChange={(e) => {
        const value = e.target.value;
        startTransition(() => {
          setSearch(value);  // Non-urgent update
          setPage(1);
        });
      }}
    />
  );
}
```

**Benefits:**
- ✅ Keeps UI responsive during data fetching
- ✅ Prioritizes urgent updates (typing) over non-urgent ones (filtering)
- ✅ Built-in loading state (`isPending`)

**Use Cases:**
- Search inputs
- Filter dropdowns
- Pagination buttons
- Any state update that triggers API calls

---

### 55. useOptimistic for Instant UI Feedback

**Why:** Enables optimistic UI updates, showing expected results immediately before server confirmation.

**Implementation:**
```typescript
import { useOptimistic } from "react";

function TodoList({ todos }: { todos: Todo[] }) {
  const [optimisticTodos, addOptimisticTodo] = useOptimistic(
    todos,
    (state, newTodo: Todo) => [...state, newTodo]
  );

  async function addTodo(formData: FormData) {
    const text = formData.get("text") as string;
    const newTodo = { id: Date.now(), text, completed: false };

    // Optimistically update UI
    addOptimisticTodo(newTodo);

    // Actually create todo
    await todoService.create(newTodo);
    refetch();  // Sync with server
  }

  return (
    <div>
      {optimisticTodos.map((todo) => (
        <div key={todo.id}>{todo.text}</div>
      ))}
    </div>
  );
}
```

**Benefits:**
- ✅ Instant UI feedback (feels faster)
- ✅ Better user experience
- ✅ Automatic rollback on error
- ✅ No need to manually manage optimistic state

**Use Cases:**
- CRUD operations (create, update, delete)
- Any operation that might take time
- Operations where instant feedback improves UX

---

### 56. useDeferredValue for Expensive Computations

**Why:** Defers updating a value until after urgent updates, improving performance for expensive operations.

**Implementation:**
```typescript
import { useDeferredValue, useMemo } from "react";

function DashboardPage() {
  const { data: allAssets } = useAssets({ page: 1, limit: 1000 });
  const assets: Asset[] = allAssets?.data ?? [];

  // Defer expensive data
  const deferredAssets = useDeferredValue(assets);

  // Memoize expensive computation
  const chartData = useMemo(() => {
    return deferredAssets.reduce((acc, asset) => {
      const status = asset.status || "Unknown";
      acc[status] = (acc[status] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
  }, [deferredAssets]);

  return <Chart data={chartData} />;
}
```

**Benefits:**
- ✅ Defers expensive computations
- ✅ Prioritizes urgent updates
- ✅ Better performance
- ✅ Automatic optimization

**Use Cases:**
- Chart calculations with large datasets (1000+ items)
- Filtering/sorting large arrays
- Expensive data transformations
- Any computation that might block UI

---

### 57. Next.js App Router Special Files

**Why:** Next.js App Router provides special files for loading states, error handling, and route organization.

**Implementation:**

#### loading.tsx - Route-Level Loading States
```typescript
// app/(dashboard)/loading.tsx
import { LoadingState } from "@/app/components/loading-state";

export default function Loading() {
  return <LoadingState message="Loading dashboard..." />;
}
```

#### error.tsx - Error Boundaries
```typescript
// app/(dashboard)/error.tsx
"use client";

import { ErrorState } from "@/app/components/loading-state";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      message={error.message || "Something went wrong"}
      onRetry={reset}
    />
  );
}
```

#### Route Groups - Organization
```
app/
├── (auth)/          # Auth route group
│   ├── layout.tsx   # Auth-specific layout
│   └── login/
│       └── page.tsx
├── (dashboard)/     # Dashboard route group
│   ├── layout.tsx   # Dashboard layout with sidebar
│   ├── loading.tsx  # Loading UI
│   ├── error.tsx    # Error boundary
│   └── page.tsx     # Dashboard home
```

**Benefits:**
- ✅ Automatic loading states during route transitions
- ✅ Centralized error handling
- ✅ Better code organization
- ✅ Shared layouts per route group

---

### 58. NextAuth.js v5 Authentication

**Why:** Complete authentication solution with session management, CSRF protection, and role-based authorization.

**Implementation:**

#### Configuration
```typescript
// lib/auth/config.ts
import NextAuth from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      async authorize(credentials) {
        const employee = await Employee.findOne({ email: credentials.email });
        const isValid = await bcrypt.compare(
          credentials.password,
          employee.password
        );
        if (!isValid) throw new Error("Invalid credentials");
        return {
          id: employee._id,
          email: employee.email,
          roles: employee.roles,
        };
      },
    }),
  ],
  session: { strategy: "jwt", maxAge: 30 * 60 },
  callbacks: {
    async jwt({ token, user }) {
      if (user) token.roles = user.roles.join(",");
      return token;
    },
    async session({ session, token }) {
      session.user.roles = (token.roles as string).split(",");
      return session;
    },
  },
};
```

#### Middleware Protection
```typescript
// middleware.ts
export function middleware(request: NextRequest) {
  const sessionToken = request.cookies.get("authjs.session-token")?.value;
  if (!sessionToken && !request.nextUrl.pathname.startsWith("/login")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}
```

**Benefits:**
- ✅ Secure authentication (password hashing, secure cookies)
- ✅ Session management (JWT or database)
- ✅ CSRF protection
- ✅ Role-based authorization
- ✅ TypeScript support

---

## Summary

These concepts form the foundation of a **production-ready, scalable, secure, and maintainable full-stack application**. Implementing these patterns will:

1. **Reduce Code Duplication** by 90%+
2. **Improve Performance** by 50-70%
3. **Enhance Security** with industry-standard protections
4. **Increase Scalability** through proper architecture
5. **Improve Maintainability** with clean, organized code
6. **Enable Testing** with testable, modular components
7. **Better UX** with React 19 hooks (useTransition, useOptimistic, useDeferredValue)
8. **Secure Auth** with NextAuth.js v5

**Priority Order:**
1. Start with **Security** (CSRF, Input Sanitization, XSS Protection, Rate Limiting, NextAuth)
2. Implement **Performance** optimizations (Pagination, Caching, Aggregation, Request Deduplication, useDeferredValue)
3. Add **Architecture Patterns** (Events, Repository, Service Layer, Design Patterns)
4. Implement **React Best Practices** (useTransition, useOptimistic, Custom Hooks, State Management)
5. Apply **SOLID Principles** (SRP, OCP, LSP, ISP, DIP)
6. Enhance with **Advanced Features** (Job Queue, Batch API)
7. Polish with **Code Quality** (Utilities, Type Safety, Testing, Eliminate Duplicates)
8. Use **Next.js App Router Features** (loading.tsx, error.tsx, route groups)
