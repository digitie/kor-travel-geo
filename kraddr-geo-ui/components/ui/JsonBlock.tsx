export function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-box">{JSON.stringify(value, null, 2)}</pre>;
}
