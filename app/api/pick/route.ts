import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const pickerUrl = 'http://localhost:3001/pick';
    const response = await fetch(pickerUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, {
      headers: { 'Access-Control-Allow-Origin': '*' },
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Picker proxy error' },
      { status: 500, headers: { 'Access-Control-Allow-Origin': '*' } }
    );
  }
}