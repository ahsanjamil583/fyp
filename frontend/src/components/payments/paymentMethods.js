export function getDefaultPaymentMethod(options = {}) {
  const methods = options.methods || [];
  if (!methods.length) return "";
  return options.defaultMethod && methods.some((method) => method.code === options.defaultMethod)
    ? options.defaultMethod
    : methods[0].code;
}

export function getSelectedPaymentMethod(options = {}, selectedCode = "") {
  return (options.methods || []).find((method) => method.code === selectedCode) || options.methods?.[0] || null;
}
