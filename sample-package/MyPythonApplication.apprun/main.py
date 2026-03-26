from frameworks.AppRun.src.usr.lib.AppRun.libs import import_test
from frameworks.AppRun.src.usr.lib.AppRun.libs.AppContext import AppContext

import_test.test()

ctx = AppContext()

print(f"Interpreter Path: {ctx.interpreter()}")
print(f"AppRun Box Path: {ctx.box()}")
print(f"Bundle ID: {ctx.id()}")
print(ctx)

