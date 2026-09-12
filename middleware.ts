import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const FC_HOST = 'fc.texasdrill.me';

const FC_ALLOWED_PREFIXES = ['/fc', '/api/fc', '/_next', '/favicon.ico'];

function isFcInstance(request: NextRequest) {
  const host = request.headers.get('host') || '';
  return host.includes(FC_HOST) || process.env.FC_INSTANCE === 'true';
}

export function middleware(request: NextRequest) {
  if (!isFcInstance(request)) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  const allowed = FC_ALLOWED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p + '?'));

  if (allowed) {
    const res = NextResponse.next();
    res.headers.set('x-fc-instance', 'true');
    return res;
  }

  if (pathname === '/') {
    return NextResponse.redirect(new URL('/fc', request.url));
  }

  return NextResponse.redirect(new URL('/fc', request.url));
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};