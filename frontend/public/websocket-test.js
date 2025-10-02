// WebSocket调试功能测试脚本
// 在浏览器控制台中运行此脚本来测试WebSocket功能

console.log('=== WebSocket调试功能测试 ===');

// 1. 检查WebSocket调试对象是否存在
if (typeof window.wsDebug !== 'undefined') {
  console.log('✅ wsDebug对象存在');
  console.log('可用的调试功能:', Object.keys(window.wsDebug));
} else {
  console.log('❌ wsDebug对象不存在（可能不在开发模式）');
}

// 2. 测试获取连接信息
try {
  const { getConnectionInfo } = window.wsDebug || {};
  if (getConnectionInfo) {
    const info = getConnectionInfo();
    console.log('📊 当前连接信息:', info);
    
    // 检查关键字段
    console.log('连接状态:', info.status);
    console.log('重连次数:', info.wsReconnectAttempts);
    console.log('是否自动重连中:', info.isAutoReconnecting);
  }
} catch (e) {
  console.error('获取连接信息失败:', e);
}

// 3. 测试发送消息功能
function testSendMessage() {
  try {
    // 测试通过useWebSocket发送消息
    const testData = {
      type: 'test',
      timestamp: Date.now(),
      message: '这是一个测试消息'
    };
    
    console.log('🚀 尝试发送测试消息:', testData);
    
    // 这里需要在实际的Vue组件中调用
    console.log('💡 提示: 请在设置页面的高级选项中使用消息测试功能');
    
  } catch (e) {
    console.error('发送消息测试失败:', e);
  }
}

// 4. 检查WebSocket连接状态
function checkWebSocketStatus() {
  try {
    const { getGlobalStorage } = window.wsDebug || {};
    if (getGlobalStorage) {
      const global = getGlobalStorage();
      console.log('🔌 WebSocket实例:', global.wsRef);
      console.log('📡 WebSocket状态:', global.wsRef?.readyState);
      
      const readyStateMap = {
        0: 'CONNECTING',
        1: 'OPEN', 
        2: 'CLOSING',
        3: 'CLOSED'
      };
      
      const state = global.wsRef?.readyState;
      console.log('状态说明:', `${state} (${readyStateMap[state] || 'UNKNOWN'})`);
    }
  } catch (e) {
    console.error('检查WebSocket状态失败:', e);
  }
}

// 运行测试
testSendMessage();
checkWebSocketStatus();

console.log('=== 测试完成 ===');
console.log('💡 更多功能请访问：设置 -> 高级设置 -> WebSocket调试');
console.log('💡 或者添加URL参数 ?debug=true 显示调试面板');