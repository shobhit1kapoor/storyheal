/**
 * 退出登录功能测试工具
 * 用于验证退出登录功能是否正常工作
 */

import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

/**
 * 测试退出登录功能
 */
export const testLogoutFunctionality = async (): Promise<void> => {
  console.log('🧪 开始测试退出登录功能...');

  try {
    // 1. 检查当前认证状态
    const authState = useAuthStore.getState();
    console.log('🧪 当前认证状态:', {
      isAuthenticated: authState.isAuthenticated,
      hasUser: !!authState.user,
      hasToken: !!authState.token
    });

    // 2. 检查聊天数据
    const chatState = useChatStore.getState();
    console.log('🧪 当前聊天数据:', {
      chatsCount: chatState.chats.length,
      messagesCount: chatState.messages.length,
      hasActiveChat: !!chatState.activeChat
    });

    // 3. 检查本地存储
    const localStorageKeys = Object.keys(localStorage);
    const relevantKeys = localStorageKeys.filter(key => 
      key.includes('auth') || 
      key.includes('chat') || 
      key.includes('storyheal')
    );
    console.log('🧪 相关的本地存储键:', relevantKeys);

    // 4. 执行退出登录
    console.log('🧪 执行退出登录...');
    await authState.logout();

    // 注意：由于logout函数会重定向页面，下面的代码可能不会执行
    console.log('🧪 退出登录完成');

  } catch (error) {
    console.error('🧪 退出登录测试失败:', error);
  }
};

/**
 * 检查退出登录后的状态
 * 这个函数应该在页面重新加载后调用
 */
export const checkLogoutState = (): void => {
  console.log('🧪 检查退出登录后的状态...');

  // 1. 检查认证状态
  const authState = useAuthStore.getState();
  console.log('🧪 退出后认证状态:', {
    isAuthenticated: authState.isAuthenticated,
    hasUser: !!authState.user,
    hasToken: !!authState.token
  });

  // 2. 检查聊天数据
  const chatState = useChatStore.getState();
  console.log('🧪 退出后聊天数据:', {
    chatsCount: chatState.chats.length,
    messagesCount: chatState.messages.length,
    hasActiveChat: !!chatState.activeChat
  });

  // 3. 检查本地存储
  const localStorageKeys = Object.keys(localStorage);
  const relevantKeys = localStorageKeys.filter(key => 
    key.includes('auth') || 
    key.includes('chat') || 
    key.includes('storyheal')
  );
  console.log('🧪 退出后本地存储键:', relevantKeys);

  // 4. 检查会话存储
  const sessionStorageKeys = Object.keys(sessionStorage);
  console.log('🧪 退出后会话存储键:', sessionStorageKeys);

  // 5. 验证结果
  const isCleanedProperly = 
    !authState.isAuthenticated &&
    !authState.user &&
    !authState.token &&
    chatState.chats.length === 0 &&
    chatState.messages.length === 0 &&
    !chatState.activeChat &&
    relevantKeys.length === 0 &&
    sessionStorageKeys.length === 0;

  console.log('🧪 退出登录清理是否完整:', isCleanedProperly ? '✅ 是' : '❌ 否');

  if (!isCleanedProperly) {
    console.warn('🧪 发现未清理的数据:', {
      authNotCleared: authState.isAuthenticated || !!authState.user || !!authState.token,
      chatNotCleared: chatState.chats.length > 0 || chatState.messages.length > 0 || !!chatState.activeChat,
      localStorageNotCleared: relevantKeys.length > 0,
      sessionStorageNotCleared: sessionStorageKeys.length > 0
    });
  }
};

/**
 * 在浏览器控制台中暴露测试函数
 */
if (typeof window !== 'undefined') {
  (window as any).testLogout = testLogoutFunctionality;
  (window as any).checkLogoutState = checkLogoutState;
  
  console.log('🧪 退出登录测试工具已加载');
  console.log('🧪 使用 testLogout() 测试退出登录功能');
  console.log('🧪 使用 checkLogoutState() 检查退出后的状态');
}
