<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'

const username = ref('')
const password = ref('')
const errorMessage = ref('')
const router = useRouter()

// 点登录时触发，暂时只打印到控制台
const handleLogin = async () => {
  errorMessage.value = ''            // 每次登录前清掉旧提示
  try {
    const response = await axios.post('/api/auth/login', {
      username: username.value,
      password: password.value
    })
    console.log('登录成功:', response.data)
    localStorage.setItem('token', response.data.access_token)  // 存 token
    router.replace('/chat')                                        // 跳转
 
  } catch (error) {
    errorMessage.value = error.response?.data?.error || '登录失败，请重试' 
  }
}

</script>

<template>
  <div class="page">
    <div class="card">

      <h1>登录</h1>

      <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>

      <form @submit.prevent="handleLogin" autocomplete="off">

        <div class="row">
          <label>用户名</label>
          <input v-model="username" type="text" placeholder="请输入用户名" autocomplete="username">
        </div>

        <div class="row">
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入密码" autocomplete="current-password">
        </div>

        <div class="row">
          <button class="btn" type="submit">登录</button>
        </div>

      </form>

      <div class="footer-link">
        <router-link to="/register" href="/register">还没有注册？去注册</router-link>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* ======== 页面背景：让卡片在屏幕正中央 ======== */
.page {
  height: 100vh;                    /* 占满整个浏览器窗口高度 */
  display: flex;                    /* 开弹性布局 */
  justify-content: center;          /* 水平居中 */
  align-items: center;              /* 垂直居中 */
  background-color: #f0f2f5;        /* 浅灰背景 */
}

/* ======== 卡片容器：白色圆角矩形 ======== */
.card {
  width: 400px;
  padding: 40px 32px;               /* 内边距：上下 40px，左右 32px */
  background-color: #fff;           /* 白色背景 */
  border-radius: 12px;              /* 圆角 */
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);  /* 阴影：水平 垂直 模糊 颜色 */
}

/* ======== 标题 ======== */
h1 {
  text-align: center;
  margin-bottom: 32px;              /* 和下面内容的间距 */
  color: #1a1a1a;
}

/* ======== 每一行（标签 + 输入框） ======== */
.row {
  margin-bottom: 20px;              /* 行与行之间的间距 */
}

label {
  display: block;                   /* 独占一行，输入框往下掉 */
  margin-bottom: 6px;
  font-size: 14px;
  color: #333;
}

input {
  width: 100%;                      /* 和父容器一样宽 */
  padding: 10px 12px;
  border: 1px solid #d9d9d9;        /* 浅灰边框 */
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;           /* padding 也算在宽度内，不会撑破 */
}

/* ======== 登录按钮 ======== */
.btn {
  width: 100%;
  padding: 10px 0;
  background-color: #1677ff;        /* 蓝色 */
  color: #fff;                      /* 白色文字 */
  border: none;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;                  /* 鼠标悬停变成手指 */
}

.btn:hover {                        /* 鼠标悬停时 */
  background-color: #4096ff;        /* 蓝色变亮 */
}

/* ======== 错误提示 ======== */
.error-msg {
  color: #ff4d4f;
  text-align: center;
  margin-bottom: 16px;
  font-size: 14px;
}

/* ======== 底部链接 ======== */
.footer-link {
  text-align: center;
  margin-top: 16px;
}

.footer-link a {
  color: #1677ff;
  text-decoration: none;            /* 去掉下划线 */
  font-size: 14px;
}

.footer-link a:hover {
  text-decoration: underline;       /* 鼠标悬停时出现下划线 */
}
</style>
