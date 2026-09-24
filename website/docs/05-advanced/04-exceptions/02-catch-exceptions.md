---
sidebar_position: 2
---

# Catch exceptions

Several OpenCascade APIs perform basic sanity checks on input parameters, like `BRepPrimAPI_MakeCone`. When calling it's constructor with a height of zero for example, OpenCascade would throw a `Standard_DomainError`, a subclass of `Standard_Failure`, with additional information about the error.

```js title="Input:"
const disc = new oc.BRepPrimAPI_MakeCone_1(1, 0, 0);
```
```_ title="Output:"
thrown: [object WebAssembly.Exception]
```

We can catch this exception in JavaScript, simple by wrapping it with a `try...catch` block. However, the thrown value is a `WebAssembly.Exception` and does not contain any meaningful information about the error.

## Extract exception data

`getExceptionMessage` takes the caught exception and returns the C++ type name and the `what()` message. Call `decrementExceptionRefcount` when you are done, or the exception object leaks.

```js title="Input:"
try {
  const disc = new oc.BRepPrimAPI_MakeCone_1(1, 0, 0);
} catch (e) {
  if (e instanceof WebAssembly.Exception) {
    const [type, message] = oc.getExceptionMessage(e);
    oc.decrementExceptionRefcount(e);
    console.log(`That didn't work because: ${type}: ${message}`);
  } else {
    console.log("Unknown error");
  }
}
```
```_ title="Output:"
That didn't work because: Standard_DomainError: cone with negative or null height
```

You can now react to the error, show it to your user and potentially retry the execution.

:::info You can disable exception support

Because of it's impact on file size and runtime performance, exception catching can be disabled if it is not required in your app. Check out the note in the [docs on file size](/docs/getting-started/file-size#what-if-thats-still-too-much).

:::

## Additional resources

* [Emscripten Docs: General information on exceptions](https://emscripten.org/docs/porting/exceptions.html)
* [Emscripten Docs: How to catch and convert exception pointers](https://emscripten.org/docs/porting/Debugging.html#handling-c-exceptions-from-javascript)