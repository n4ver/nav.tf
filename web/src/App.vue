<template>
  <div>
    <nav class="top-nav">
      <RouterLink to="/" class="nav-link">Tournament</RouterLink>
      <RouterLink to="/match" class="nav-link">Match Statistics</RouterLink>
      <RouterLink to="/player" class="nav-link">Player Statistics</RouterLink>
    </nav>
    <RouterView />
  </div>
</template>
