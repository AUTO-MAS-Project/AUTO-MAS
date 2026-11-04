# 行为断言与用例规模

## 两个检查决定测试是否有价值

测试可以位于公共函数、组件、接口或端到端入口，不强制使用完整集成环境。选择调用方实际依赖的契约，并用两个问题检查：

- 把结果改错、漏掉副作用或执行两次，测试是否会失败？若不会，收紧断言或改用正确入口。
- 保持契约不变，只重构内部实现，测试是否仍然通过？若不会，移除对内部结构的绑定。

断言可以共同证明一个行为，无需按断言数量拆分用例。对“重试成功只通知一次”，结果正确与通知次数可以在同一个测试中验证。

## 公共接口与可观察副作用

通过真实公共接口执行被测逻辑：

```typescript
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

内部支付辅助函数被调用并不能证明结算完成。下面的断言绑定了实现：

```typescript
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

如果契约是“不重复扣款”，在支付服务边界记录请求次数与金额就是有效行为断言；不能把所有调用次数断言都当作坏测试。不要 mock 内部辅助函数后仅断言这个 mock 被调用。

有公开读取接口时，用它检查写入结果；契约本身是持久化、发送请求或生成文件时，也可直接检查隔离存储、边界请求或文件内容，无需只为测试新增读取接口。

```typescript
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

## 独立预期

预期来自需求或已核实实例，不重复被测算法，也不从当前输出来生成答案：

```typescript
// BAD: Expected value is recomputed the way the code computes it
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// GOOD: Expected value is an independent, known literal
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```

## 控制用例规模

- 一个独立行为使用最小可读场景；多个输入保护不同边界时可参数化。输入不同不等于新增覆盖价值，也不要求每个分支或每个函数都有测试。
- 相同风险已由其他层证明时，复用已有覆盖；只有某层存在独有契约时才增加该层检查。
- 不读取业务源码再断言其中出现某个字符串、分支或函数名。前端的少量跨语言契约与仓库扫描例外按 `mas-frontend-standards` 执行。
- 审查既有测试时仍按其契约判断，不能为减少数量或让重构通过而削弱有效断言。
